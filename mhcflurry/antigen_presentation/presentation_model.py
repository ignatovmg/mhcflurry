import collections
import time
from copy import copy
import logging

import pandas
import numpy

from sklearn.base import clone
from sklearn.model_selection import StratifiedKFold
from sklearn.linear_model import LogisticRegression

from ..common import assert_no_null, drop_nulls_and_warn


def build_presentation_models(term_dict, formulas, **kwargs):
    """
    Convenience function for creating multiple final models based on
    shared terms.

    Parameters
    ------------
    term_dict : dict of string -> (
            list of PresentationComponentModel,
            list of string)
        Terms are named with arbitrary strings (e.g. "A_ms") and are
        associated with some presentation component models and some
        expressions (e.g. ["log(affinity_percentile_rank + .001)"]).

    formulas : list of string
        A formula is a string containing terms separated by "+". For example:
        "A_ms + A_cleavage + A_expression".

    **kwargs : dict
        Passed to PresentationModel constructor

    Returns
    ------------

    dict of string -> PresentationModel

    The keys of the result dict are formulas, and the values are (untrained)
    PresentationModel instances.
    """
    result = collections.OrderedDict()

    for formula in formulas:
        term_names = [x.strip() for x in formula.split("+")]
        inputs = []
        expressions = []
        for name in term_names:
            (term_inputs, term_expressions) = term_dict[name]
            inputs.extend(term_inputs)
            expressions.extend(term_expressions)
        assert len(set(expressions)) == len(expressions)
        presentation_model = PresentationModel(
            inputs,
            expressions,
            **kwargs)
        result[formula] = presentation_model
    return result


class PresentationModel(object):
    """
    A predictor for whether a peptide is detected via mass-spec. Uses
    "final model inputs" (e.g. expression, cleavage, mhc affinity) which
    themselves may need to be fit.

    Parameters
    ------------
    component_models : list of PresentationComponentModel

    feature_expressions : list of string
        Expressions to use to generate features for the final model based
        on the columns generated by the final model inputs.

        Example: ["log(expression + .01)"]

    decoy_strategy : DecoyStrategy
        Decoy strategy to use for training the final model. (The final
        model inputs handle their own decoys.)

    random-state : int
        Random state to use for picking cross validation folds. We are
        careful to be deterministic here (i.e. same folds used if the
        random state is the same) because we want to have cache hits
        for final model inputs that are being used more than once in
        multiple final models fit to the same data.

    ensemble_size : int
        If specified, train an ensemble of each final model input, and use
        the out-of-bag predictors to generate predictions to fit the final
        model. If not specified (default), a two-fold fit is used.

    """
    def __init__(
            self,
            component_models,
            feature_expressions,
            decoy_strategy,
            predictor=LogisticRegression(),
            random_state=0,
            ensemble_size=None):
        columns = set()
        self.component_models_require_fitting = False
        for component_model in component_models:
            model_cols = component_model.column_names()
            assert not columns.intersection(model_cols), model_cols
            columns.update(model_cols)
            if component_model.requires_fitting():
                self.component_models_require_fitting = True

        self.component_models = component_models
        self.ensemble_size = ensemble_size

        self.feature_expressions = feature_expressions
        self.decoy_strategy = decoy_strategy
        self.random_state = random_state
        self.predictor = predictor

        self.trained_component_models = None
        self.presentation_models_predictors = None
        self.fit_experiments = None

    @property
    def has_been_fit(self):
        return self.fit_experiments is not None

    def clone(self):
        return copy(self)

    def reset_cache(self):
        for model in self.component_models:
            model.reset_cache()
        if self.trained_component_models is not None:
            for models in self.trained_component_models:
                for model in models:
                    model.reset_cache()

    def fit(self, hits_df):
        """
        Train the final model and its inputs (if necessary).

        Parameters
        -----------
        hits_df : pandas.DataFrame
            dataframe of hits with columns 'experiment_name' and 'peptide'
        """
        start = time.time()
        assert not self.has_been_fit
        assert 'experiment_name' in hits_df.columns
        assert 'peptide' in hits_df.columns

        assert self.trained_component_models is None
        assert self.presentation_models_predictors is None

        hits_df = hits_df.reset_index(drop=True)
        self.fit_experiments = set(hits_df.experiment_name.unique())

        if self.component_models_require_fitting and not self.ensemble_size:
            # Use two fold CV to train model inputs then final models.
            cv = StratifiedKFold(
                n_splits=2, shuffle=True, random_state=self.random_state)

            self.trained_component_models = []
            self.presentation_models_predictors = []
            fold_num = 1
            for (fold1, fold2) in cv.split(hits_df, hits_df.experiment_name):
                print("Two fold fit: fitting fold %d" % fold_num)
                fold_num += 1
                assert len(fold1) > 0
                assert len(fold2) > 0
                model_input_training_hits_df = hits_df.iloc[fold1]

                self.trained_component_models.append([])
                for sub_model in self.component_models:
                    sub_model = sub_model.clone_and_fit(
                        model_input_training_hits_df)
                    self.trained_component_models[-1].append(sub_model)

                final_predictor = self.fit_final_predictor(
                    hits_df.iloc[fold2],
                    self.trained_component_models[-1])
                self.presentation_models_predictors.append(final_predictor)
        elif self.component_models_require_fitting:
            print("Using ensemble fit, ensemble size: %d" % self.ensemble_size)
            raise NotImplementedError()

            '''
            hits_in_train = pandas.DataFrame(index=hits_df.index)
            out_of_sample_predictions = [
                []
                for _ in self.component_models
            ]
            for i in range(self.ensemble_size):
                print("Training ensemble %d / %d" % (
                    i + 1, self.ensemble_size))

                train_mask = numpy.random.randint(2, size=len(hits_df))

                model_input_training_hits_df = hits_df.ix[train_mask]
                presentation_model_training_hits_df = hits_df.ix[~train_mask]

                hits_and_decoys_df = make_hits_and_decoys_df(
                    presentation_model_training_hits_df,
                    self.decoy_strategy)

                self.trained_component_models.append([])
                out_of_sample_predictions.append([])
                for sub_model in self.component_models:
                    sub_model = sub_model.clone_and_fit(
                        model_input_training_hits_df)
                    self.trained_component_models[-1].append(sub_model)

                    predictions = sub_model.predict(presentation_model_training_hits_df)
                    for (col, values) in predictions.items():
                        presentation_model_training_hits_df[col] = values
                    out_of_sample_predictions[-1].append()

            hits_and_decoys_df = make_hits_and_decoys_df(
                hits_df,
                self.decoy_strategy)

            for sub_model in component_models:
                predictions = sub_model.predict(hits_and_decoys_df)
                for (col, values) in predictions.items():
                    hits_and_decoys_df[col] = values

            (x, y) = self.make_features_and_target(hits_and_decoys_df)
            print("Training final model predictor on data of shape %s" % (
                str(x.shape)))
            final_predictor = clone(self.predictor)
            final_predictor.fit(x.values, y.values)
            self.presentation_models_predictors.append(final_predictor)
            '''
        else:
            print("Using single-fold fit.")
            # Use full data set to train final model.
            final_predictor = self.fit_final_predictor(
                hits_df,
                self.component_models)

            assert not self.presentation_models_predictors
            self.presentation_models_predictors = [final_predictor]
            self.trained_component_models = [
                self.component_models
            ]

        assert len(self.presentation_models_predictors) == \
            len(self.trained_component_models)

        print("Fit final model in %0.1f sec." % (time.time() - start))

        # Decoy strategy is no longer required after fitting.
        self.decoy_strategy = None

    def fit_final_predictor(self, hits_df, component_models):
        """
        Private helper method.
        """
        hits_and_decoys_df = make_hits_and_decoys_df(
            hits_df,
            self.decoy_strategy)

        for sub_model in component_models:
            predictions = sub_model.predict(hits_and_decoys_df)
            for (col, values) in predictions.items():
                hits_and_decoys_df[col] = values

        (x, y) = self.make_features_and_target(hits_and_decoys_df)
        print("Training final model predictor on data of shape %s" % (
            str(x.shape)))
        final_predictor = clone(self.predictor)
        final_predictor.fit(x.values, y.values)

        return final_predictor

    def evaluate_expressions(self, input_df):
        result = pandas.DataFrame()
        for expression in self.feature_expressions:
            # We use numpy module as globals here so math functions
            # like log, log1p, exp, are in scope.
            values = eval(expression, numpy.__dict__, input_df)
            assert len(values) == len(input_df), expression
            if hasattr(values, 'values'):
                values = values.values
            series = pandas.Series(values)
            assert_no_null(series, expression)
            result[expression] = series
        assert len(result) == len(input_df)
        return result

    def make_features_and_target(self, hits_and_decoys_df):
        """
        Private helper method.
        """
        assert 'peptide' in hits_and_decoys_df
        assert 'hit' in hits_and_decoys_df

        df = self.evaluate_expressions(hits_and_decoys_df)
        df['hit'] = hits_and_decoys_df.hit.values
        new_df = drop_nulls_and_warn(df, hits_and_decoys_df)
        y = new_df["hit"]
        del new_df["hit"]
        return (new_df, y)

    def predict_to_df(self, peptides_df):
        """
        Predict for the given peptides_df, which should have columns
        'experiment_name' and 'peptide'.

        Returns a dataframe giving the predictions. If this final
        model's inputs required fitting and therefore the final model
        has two predictors trained each fold, the resulting dataframe
        will have predictions for both final model predictors.
        """
        assert self.has_been_fit
        assert 'experiment_name' in peptides_df.columns
        assert 'peptide' in peptides_df.columns
        assert len(self.presentation_models_predictors) == \
            len(self.trained_component_models)

        prediction_cols = []
        presentation_model_predictions = {}
        zipped = enumerate(
            zip(
                self.trained_component_models,
                self.presentation_models_predictors))
        for (i, (component_models, presentation_model_predictor)) in zipped:
            df = pandas.DataFrame()
            for sub_model in component_models:
                start_t = time.time()
                predictions = sub_model.predict(peptides_df)
                print("Input '%s' generated %d predictions in %0.2f sec." % (
                    sub_model, len(peptides_df), (time.time() - start_t)))
                for (col, values) in predictions.items():
                    values = pandas.Series(values)
                    assert_no_null(values)
                    df[col] = values

            x_df = self.evaluate_expressions(df)
            assert_no_null(x_df)

            prediction_col = "Prediction (Model %d)" % (i + 1)
            assert prediction_col not in presentation_model_predictions
            presentation_model_predictions[prediction_col] = (
                presentation_model_predictor
                .predict_proba(x_df.values)[:, 1])
            prediction_cols.append(prediction_col)

        if len(prediction_cols) == 1:
            presentation_model_predictions["Prediction"] = (
                presentation_model_predictions[prediction_cols[0]])
            del presentation_model_predictions[prediction_cols[0]]
        else:
            presentation_model_predictions["Prediction"] = numpy.mean(
                [
                    presentation_model_predictions[col]
                    for col in prediction_cols
                ],
                axis=0)

        return pandas.DataFrame(presentation_model_predictions)

    def predict(self, peptides_df):
        """
        Predict for the given peptides_df, which should have columns
        'experiment_name' and 'peptide'.

        Returns an array of floats giving the predictions for each
        row in peptides_df. If the final model was trained in two
        folds, the predictions from the two final model predictors
        are averaged.
        """
        assert self.has_been_fit
        df = self.predict_to_df(peptides_df)
        return df.Prediction.values

    def score_from_peptides_df(
            self, peptides_df, include_hit_indices=True):
        """
        Given a DataFrame with columns 'peptide', 'experiment_name', and
        'hit', calculate the PPV score. Return a dict of scoring info.

        If include_hit_indices is True (default), then the indices the
        hits occur in after sorting by prediction score, is also returned.
        The top predicted peptide will have index 0.
        """
        assert self.has_been_fit
        assert 'peptide' in peptides_df.columns
        assert 'experiment_name' in peptides_df.columns
        assert 'hit' in peptides_df.columns

        peptides_df["prediction"] = self.predict(peptides_df)
        # print(sorted(peptides_df.prediction[peptides_df.hit].values))
        top_n = float(peptides_df.hit.sum())

        if not include_hit_indices:
            top = peptides_df.nlargest(top_n, "prediction")
            result = {
                'score': top.hit.mean()
            }
        else:
            ranks = peptides_df.prediction.rank(ascending=False)
            result = {
                'hit_indices': numpy.sort(ranks[peptides_df.hit > 0].values),
                'total_peptides': len(peptides_df),
            }
            result['score'] = (
                numpy.sum(result['hit_indices'] <= top_n) / top_n)
        return result

    def score_from_hits_and_decoy_strategy(self, hits_df, decoy_strategy):
        """
        Compute positive predictive value on the given hits_df.

        Parameters
        -----------
        hits_df : pandas.DataFrame
            dataframe of hits with columns 'experiment_name' and 'peptide'

        decoy_strategy : DecoyStrategy
            Strategy for selecting decoys

        Returns
        -----------

        dict of scoring info, with keys 'score', 'hit_indices', and
        'total_peptides'
        """
        assert self.has_been_fit
        peptides_df = make_hits_and_decoys_df(
            hits_df,
            decoy_strategy)
        return self.score_from_peptides_df(peptides_df)

    def get_fit(self):
        """
        Return fit (i.e. trained) parameters.
        """
        assert self.has_been_fit
        result = {
            'trained_component_model_fits': [],
            'presentation_models_predictors': (
                self.presentation_models_predictors),
            'fit_experiments': self.fit_experiments,
            'feature_expressions': self.feature_expressions,
        }
        for models in self.trained_component_models:
            result['trained_component_model_fits'].append([
                component_model.get_fit()
                for component_model in models
            ])
        return result

    def restore_fit(self, fit):
        """
        Restore fit parameters.

        Parameters
        ------------
        fit : object
            What was returned from a call to get_fit().

        """
        assert not self.has_been_fit
        fit = dict(fit)
        self.presentation_models_predictors = (
            fit.pop('presentation_models_predictors'))
        self.fit_experiments = fit.pop('fit_experiments')
        model_input_fits = fit.pop('trained_component_model_fits')
        feature_expressions = fit.pop('feature_expressions', [])
        if feature_expressions != self.feature_expressions:
            logging.warn(
                "Feature expressions restored from fit: '%s' do not match "
                "those of this PresentationModel: '%s'" % (
                    feature_expressions, self.feature_expressions))
        assert not fit, "Unhandled data in fit: %s" % fit
        assert len(model_input_fits) == (
            2 if self.component_models_require_fitting else 1), (
            "Wrong length: %s" % model_input_fits)

        self.trained_component_models = []
        for model_input_fits_for_fold in model_input_fits:
            self.trained_component_models.append([])
            for (sub_model, sub_model_fit) in zip(
                    self.component_models,
                    model_input_fits_for_fold):
                sub_model = sub_model.clone_and_restore_fit(sub_model_fit)
                self.trained_component_models[-1].append(
                    sub_model)

        assert len(self.trained_component_models) == (
            2 if self.component_models_require_fitting else 1), (
            "Wrong length: %s" % self.trained_component_models)


def make_hits_and_decoys_df(hits_df, decoy_strategy):
    """
    Given some hits (with columns 'experiment_name' and 'peptide'),
    and a decoy strategy, return a "peptides_df", which has columns
    'experiment_name', 'peptide', and 'hit.'
    """
    hits_df = hits_df.copy()
    hits_df["hit"] = 1

    decoys_df = decoy_strategy.decoys(hits_df)
    decoys_df["hit"] = 0

    peptides_df = pandas.concat(
        [hits_df, decoys_df],
        ignore_index=True)
    return peptides_df
