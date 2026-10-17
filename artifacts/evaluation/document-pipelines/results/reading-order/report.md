# Reading-order benchmark: 100-page development diagnostic

**Status:** 100 development pages and 1,031 ordered reference blocks are assistant-adjudicated and scored against all three saved pipeline outputs. The target page count is met; this remains a development diagnostic, not a locked-test result. Labels are not independently human-reviewed.

## Reference and scoring

The reference uses pages also present in the full-page layout reference. Order was assigned from source images without using pipeline output order. Each index points to a zero-based annotation position in the layout reference. The scorer uses class-aware, one-to-one greedy IoU matching at 0.50. Pairwise accuracy compares relative order among matched blocks only when the pipeline provides a distinct order; read it with reference coverage.

The last nine pages added are LAYOUTV2-044, -046, -049, -050, -051, -052, -068, -071, and -092. Their order notes describe the column flow or excluded page furniture; order was assigned from source images independently of pipeline output.

## Results

| Pipeline | Matched/reference blocks | Reference coverage | Extra predictions | Matched blocks without order | Correct pairs | Pairwise accuracy |
|---|---:|---:|---:|---:|---:|---:|
| pp-structurev3 | 604/1,031 | 58.6% | 443 | 79 | 2,172/2,244 (96.8%) | 96.8% |
| mineru | 808/1,031 | 78.4% | 524 | 0 | 4,217/4,339 (97.2%) | 97.2% |
| docling | 746/1,031 | 72.4% | 472 | 0 | 3,488/3,566 (97.8%) | 97.8% |

Pairwise accuracy is conditional on matched blocks; it does not measure whether regions were detected. Reading order is scored on the 100-page development subset only, and this conditional metric does not establish a pipeline winner. All results are assistant-adjudicated diagnostics, not independent human evaluation.
