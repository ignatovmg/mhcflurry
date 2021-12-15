#!/bin/bash
set -e

SRCDIR=$(pwd)
WDIR=$(pwd)/data
mkdir -p $WDIR

#if [ '1' ]; then

mkdir -p $WDIR/mhcflurry_data/allele_sequences && cd $WDIR/mhcflurry_data/allele_sequences
if [ ! -f allele_sequences.20191231.tar.bz2 ]; then
    wget https://github.com/openvax/mhcflurry/releases/download/1.4.0/allele_sequences.20191231.tar.bz2
fi
tar xvf allele_sequences.20191231.tar.bz2
cd -

cd $WDIR
wget https://www.iedb.org/downloader.php?file_name=doc/mhc_ligand_full_single_file.zip
rm -f mhc_ligand_full.zip
mv 'downloader.php?file_name=doc%2Fmhc_ligand_full_single_file.zip' mhc_ligand_full.zip
unzip mhc_ligand_full.zip
cd -

mkdir -p $WDIR/mhcflurry_data/data_iedb && cd $WDIR/mhcflurry_data/data_iedb
if [ ! -f data_iedb.20200427.tar.bz2 ]; then
    wget https://github.com/openvax/mhcflurry/releases/download/pre-1.7.0/data_iedb.20200427.tar.bz2
fi
tar xvf data_iedb.20200427.tar.bz2
cd -

cd $SRCDIR/../downloads-generation/data_curated 
python curate.py \
     --data-iedb $WDIR/mhc_ligand_full.csv \
     --class1-pseudosequences-csv $WDIR/mhcflurry_data/allele_sequences/class1_pseudosequences.csv \
     --allele-sequences-nodiff-csv $WDIR/mhcflurry_data/allele_sequences/allele_sequences.no_differentiation.csv \
     --allele-sequences-csv $WDIR/mhcflurry_data/allele_sequences/allele_sequences.csv \
     --out-csv $WDIR/generated/iedb_curated_all.csv \
     --out-affinity-csv $WDIR/generated/iedb_curated_affinity.csv \
     --out-mass-spec-csv $WDIR/generated/iedb_curated_ms.csv
     
python $SRCDIR/add_post_mhcflurry_col.py \
    $WDIR/generated/iedb_curated_all.csv \
    $WDIR/mhcflurry_data/data_iedb/mhc_ligand_full.csv.bz2
python $SRCDIR/add_post_mhcflurry_col.py \
    $WDIR/generated/iedb_curated_affinity.csv \
    $WDIR/mhcflurry_data/data_iedb/mhc_ligand_full.csv.bz2
python $SRCDIR/add_post_mhcflurry_col.py \
    $WDIR/generated/iedb_curated_ms.csv \
    $WDIR/mhcflurry_data/data_iedb/mhc_ligand_full.csv.bz2

bzip2 -f $WDIR/generated/iedb_curated_all.csv
bzip2 -f $WDIR/generated/iedb_curated_affinity.csv
bzip2 -f $WDIR/generated/iedb_curated_ms.csv
cd -

mkdir -p $WDIR/mhcflurry_data/data_curated && cd $WDIR/mhcflurry_data/data_curated
if [ ! -f data_curated.20200427.tar.bz2 ]; then
    wget https://github.com/openvax/mhcflurry/releases/download/pre-1.7.0/data_curated.20200427.tar.bz2
fi
tar xvf data_curated.20200427.tar.bz2
cd -

mkdir -p $WDIR/mhcflurry_data/data_references && cd $WDIR/mhcflurry_data/data_references
if [ ! -f data_references.20190927.tar.bz2 ]; then
    wget https://github.com/openvax/mhcflurry/releases/download/pre-1.4.0/data_references.20190927.tar.bz2
fi
tar xvf data_references.20190927.tar.bz2
cd -

#fi

cd $SRCDIR/../downloads-generation/data_mass_spec_annotated 
python annotate.py \
    $WDIR/generated/iedb_curated_ms.csv.bz2 \
    $WDIR/mhcflurry_data/data_references/uniprot_proteins.csv.bz2 \
    $WDIR/mhcflurry_data/data_references/uniprot_proteins.fm \
    --out $WDIR/generated/iedb_annotated_ms.csv
bzip2 -f $WDIR/generated/iedb_annotated_ms.csv
cd -

cd $SRCDIR/../downloads-generation/data_predictions
python write_proteome_peptides.py \
    $WDIR/generated/iedb_annotated_ms.csv.bz2 \
    $WDIR/mhcflurry_data/data_references/uniprot_proteins.csv.bz2 \
    --lengths 8 9 10 11 12 13 14 15 \
    --out $WDIR/generated/iedb_proteome_peptides.csv # --debug-max-rows 10
bzip2 -f $WDIR/generated/iedb_proteome_peptides.csv
cd -

#cd mhcflurry/downloads-generation/models_class1_processing
#python annotate_hits_with_expression.py \
#    --hits $WDIR/generated/iedb_annotated.csv.bz2 \
#    --expression $WDIR/mhcflurry_data/data_curated/rna_expression.csv.bz2 \
#    --out $WDIR/generated/iedb_annotated_with_tpm.csv
#bzip2 -f $WDIR/generated/iedb_annotated_with_tpm.csv
#cd -

