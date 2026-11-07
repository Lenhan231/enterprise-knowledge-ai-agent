# First labeled evidence-page rank in the full corpus

Ranks are recomputed from saved vectors. A rank over 10 is a miss at the reported cutoff.
A page hit does not guarantee that the chunk contains the answer.

| Query | Direction | bge-m3 | multilingual-e5-base | qwen3-embedding-0.6b |
|---|---|---:|---:|---:|
| Q01-vi | vi->en | 28 | 59 | 88 |
| Q01-en | en->en | 33 | 15 | 63 |
| Q02-vi | vi->en | 1 | 9 | 3 |
| Q02-en | en->en | 1 | 19 | 5 |
| Q03-vi | vi->en | 112 | 98 | 130 |
| Q03-en | en->en | 132 | 131 | 123 |
| Q04-vi | vi->en | 1 | 1 | 1 |
| Q04-en | en->en | 1 | 1 | 1 |
| Q05-vi | vi->en | 1 | 1 | 1 |
| Q05-en | en->en | 1 | 1 | 2 |
| Q06-vi | vi->en | 26 | 8 | 14 |
| Q06-en | en->en | 25 | 26 | 51 |
| Q07-vi | vi->en | 35 | 5 | 32 |
| Q07-en | en->en | 27 | 12 | 65 |
| Q08-vi | vi->en | 3 | 1 | 1 |
| Q08-en | en->en | 3 | 3 | 1 |
| Q09-vi | vi->en | 16 | 4 | 4 |
| Q09-en | en->en | 20 | 7 | 15 |
| Q10-vi | vi->en | 1 | 2 | 2 |
| Q10-en | en->en | 2 | 1 | 1 |
| Q11-vi | vi->en | 37 | 74 | 17 |
| Q11-en | en->en | 20 | 65 | 21 |
| Q12-vi | vi->en | 25 | 211 | 31 |
| Q12-en | en->en | 36 | 33 | 35 |
| Q13-vi | vi->vi | 2 | 1 | 1 |
| Q13-en | en->vi | 2 | 2 | 4 |
| Q14-vi | vi->vi | 1 | 1 | 1 |
| Q14-en | en->vi | 4 | 17 | 6 |
| Q15-vi | vi->vi | 1 | 1 | 1 |
| Q15-en | en->vi | 3 | 15 | 3 |
| Q16-vi | vi->vi | 20 | 14 | 31 |
| Q16-en | en->vi | 17 | 19 | 38 |
| Q17-vi | vi->vi | 14 | 11 | 36 |
| Q17-en | en->vi | 18 | 21 | 42 |
| Q18-vi | vi->vi | 5 | 6 | 1 |
| Q18-en | en->vi | 6 | 32 | 5 |
| Q19-vi | vi->vi | 7 | 9 | 1 |
| Q19-en | en->vi | 9 | 41 | 4 |
| Q20-vi | vi->vi | 1 | 2 | 4 |
| Q20-en | en->vi | 3 | 53 | 6 |
| Q21-vi | vi->vi | 1 | 1 | 16 |
| Q21-en | en->vi | 6 | 45 | 25 |
| Q22-vi | vi->vi | 10 | 2 | 3 |
| Q22-en | en->vi | 1 | 14 | 2 |
| Q23-vi | vi->mixed | 21 | 6 | 5 |
| Q23-en | en->mixed | 19 | 29 | 4 |
| Q24-vi | vi->mixed | 4 | 19 | 1 |
| Q24-en | en->mixed | 19 | 3 | 1 |
