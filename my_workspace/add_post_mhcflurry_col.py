import pandas as pd
import sys

iedb_curated_csv = sys.argv[1]
iedb_mhcflurry_csv = sys.argv[2]

iedb_curated_df = pd.read_csv(iedb_curated_csv)
iedb_mhcflurry_df = pd.read_csv(iedb_mhcflurry_csv, skiprows=1, low_memory=False)
mhcflurry_refs = set(iedb_mhcflurry_df['Reference IRI'].values)

iedb_curated_df['post_mhcflurry_2.0'] = iedb_curated_df.reference.map(lambda x: x not in mhcflurry_refs)
iedb_curated_df.to_csv(iedb_curated_csv, index=False)