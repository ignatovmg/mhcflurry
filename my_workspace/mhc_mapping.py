import pandas as pd
import sys
import gzip
import pandas as pd
from tqdm import tqdm
from collections import defaultdict

aligned_fasta = sys.argv[1]
out_csv = sys.argv[2]

posititions_34 = '227 229 246 269 293 296 297 300 301 303 304 307 308 310 311 314 315 319 331 333 335 352 395 397 473 478 481 484 489 491 492 496 500 504'
posititions_34 = list(map(int, posititions_34.split()))

posititions_37 = '227 229 246 269 293 296 297 300 301 303 304 307 308 310 311 314 315 319 326 331 333 335 339 352 395 397 473 478 481 484 489 491 492 496 500 504 609'
posititions_37 = list(map(int, posititions_37.split()))

allele_to_aln = defaultdict(list)
with gzip.open(aligned_fasta, 'rb') as f:
    for line in f:
        line = line.decode('utf-8')
        if line.startswith('>'):
            key = line.split()[1]
            continue
        allele_to_aln[key].append(line.strip())
        
allele_to_aln = {x: ''.join(y) for x, y in allele_to_aln.items()}

def get_mapping(posititions, aln):
    mapping = []
    counter = 0
    for i, letter in enumerate(aln):
        if i in posititions:
            if letter != '-':
                mapping.append(str(counter))
            else:
                mapping.append('-')
        if letter != '-':
            counter += 1
    return mapping

alleles_out = []
for allele, aln in tqdm(allele_to_aln.items()):
    entry = {
        'allele': allele,
        'sequence': aln.replace('-', ''),
        'pseudosequence_mhcflurry_34': ''.join([aln.replace('-', 'X')[x] for x in posititions_34]),
        'pseudosequence_mhcflurry_34_positions_zerobased': ','.join(get_mapping(posititions_34, aln)),
        'pseudosequence_mhcflurry_37': ''.join([aln.replace('-', 'X')[x] for x in posititions_37]),
        'pseudosequence_mhcflurry_37_positions_zerobased': ','.join(get_mapping(posititions_37, aln))
    }
    alleles_out.append(entry)
    
pd.DataFrame(alleles_out).to_csv(out_csv, index=False)