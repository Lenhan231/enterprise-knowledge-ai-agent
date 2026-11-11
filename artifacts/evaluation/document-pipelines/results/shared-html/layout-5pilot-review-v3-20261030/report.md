# Layout detector comparison — layout-5pilot-review-v3

Same five source pages, saved detector outputs, and IoU 0.50. No post-processing or heuristic was applied.

Primary score is macro-F1 over table, text, and title; micro precision/recall/F1 are shown alongside per-class scores. Figure and page-furniture scores and unmatched predictions are reported separately.

| Candidate | Priority macro-F1 | Priority micro P/R/F1 | Table F1 | Text F1 | Title F1 | Priority FP | Figure/page-furniture FP | Other |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| pp-doclayout-l-conf040 | 57.5% | 38.7%/60.0%/47.1% | 100.0% | 29.6% | 42.9% | 19 | 18 | 0 |
| heron | 47.6% | 27.0%/50.0%/35.1% | 100.0% | 20.7% | 22.2% | 27 | 15 | 2 |
| doclayout-yolo-conf040 | 47.3% | 42.1%/40.0%/41.0% | 100.0% | 13.3% | 28.6% | 11 | 0 | 0 |
| doclayout-yolo-conf025 | 45.1% | 33.3%/40.0%/36.4% | 100.0% | 11.8% | 23.5% | 16 | 0 | 0 |
| pp-doclayout-s-conf040 | 39.1% | 29.2%/35.0%/31.8% | 75.0% | 24.0% | 18.2% | 17 | 8 | 0 |
| egret-medium | 35.1% | 6.9%/40.0%/11.8% | 100.0% | 5.3% | 0.0% | 108 | 15 | 1 |

## Localization vs label diagnosis

Diagnostic only: one-to-one box matching across table/text/title regardless of class, at the same IoU. Cross-label pairs indicate localization that succeeded but classification disagreed; these do not count as true positives in the benchmark score.

| Candidate | Localization matches / references | Localization precision / recall | Cross-label pairs |
|---|---:|---:|---:|
| pp-doclayout-l-conf040 | 18 / 20 | 58.1% / 90.0% | text->title: 6 |
| heron | 15 / 20 | 40.5% / 75.0% | text->title: 5 |
| doclayout-yolo-conf040 | 12 / 20 | 63.2% / 60.0% | text->title: 4 |
| doclayout-yolo-conf025 | 13 / 20 | 54.2% / 65.0% | text->title: 5 |
| pp-doclayout-s-conf040 | 11 / 20 | 45.8% / 55.0% | text->title: 4 |
| egret-medium | 14 / 20 | 12.1% / 70.0% | text->title: 6 |

## Findings and 5-page expansion gate

Best priority macro-F1 is **57.5%** (`pp-doclayout-l-conf040`), below the **85%** gate; the next five-page batch is therefore not opened.
For `pp-doclayout-l-conf040`, label-agnostic matching localizes 18/20 priority regions, while label-aware scoring accepts fewer. Cross-label pairs: text->title 6. Its table F1 is 100.0%, but it emits 17 unmatched text boxes.
The audited boxes show the main remaining errors are title regions classified as text and surplus text regions on table contents/marginal clutter. The p24 reference was tightened to visible text extents; labels and IoU threshold remained fixed.

## Per-class counts

TP / predictions / references; unmatched detector boxes are false positives.

### pp-doclayout-l-conf040

Source run: `layout-candidate-pp-doclayout-l-20261030`; model: `PP-DocLayout-L`; device: `cpu`; confidence/score threshold: `0.4`.

| Label | TP / predicted / reference | Precision | Recall | F1 | False positives |
|---|---:|---:|---:|---:|---:|
| table | 5 / 5 / 5 | 100.0% | 100.0% | 100.0% | 0 |
| text | 4 / 21 / 6 | 19.0% | 66.7% | 29.6% | 17 |
| title | 3 / 5 / 9 | 60.0% | 33.3% | 42.9% | 2 |
| figure | 3 / 3 / 12 | 100.0% | 25.0% | 40.0% | 0 |
| page_furniture | 1 / 19 / 10 | 5.3% | 10.0% | 6.9% | 18 |

False positive summary (all coordinates and nearest IoU values are in `evaluation.json`):

- `text`: 17 FP. Examples: `E2E-BAO-HO-LAO-DONG-2009-p13` `[0.9658246208639706, 0.58439098622611, 0.9844833473754085, 0.6986463063123219]` IoU `0.00`; `E2E-BAO-HO-LAO-DONG-2009-p13` `[0, 0.0030285417750576847, 0.04578729766646242, 0.9813494415138295]` IoU `0.00`
- `title`: 2 FP. Examples: `E2E-BAO-HO-LAO-DONG-2009-p13` `[0.7568414426317402, 0.12378854199126009, 0.8883316738153595, 0.13514609486289172]` IoU `0.00`; `E2E-LONG-HAU-2008-p17` `[0.1036171144054782, 0.6098792866686461, 0.14586737848097278, 0.9497642100282067]` IoU `0.00`
- `page_furniture`: 18 FP. Examples: `E2E-BAO-HO-LAO-DONG-2009-p13` `[0.15236088372523487, 0.9458168949949549, 0.8706189523335376, 0.9571063701923077]` IoU `0.39`; `E2E-BAO-HO-LAO-DONG-2009-p13` `[0.15554921268637664, 0.034809340778579057, 0.5940359876046772, 0.047995390715422456]` IoU `0.24`
- Unclassified `other` boxes: 0

### heron

Source run: `docling-pilot-5-layout-detector-20261029`; model: `Layout heron`; device: `CPU`; confidence/score threshold: `not recorded`.

| Label | TP / predicted / reference | Precision | Recall | F1 | False positives |
|---|---:|---:|---:|---:|---:|
| table | 5 / 5 / 5 | 100.0% | 100.0% | 100.0% | 0 |
| text | 3 / 23 / 6 | 13.0% | 50.0% | 20.7% | 20 |
| title | 2 / 9 / 9 | 22.2% | 22.2% | 22.2% | 7 |
| figure | 2 / 4 / 12 | 50.0% | 16.7% | 25.0% | 2 |
| page_furniture | 2 / 15 / 10 | 13.3% | 20.0% | 16.0% | 13 |

False positive summary (all coordinates and nearest IoU values are in `evaluation.json`):

- `text`: 20 FP. Examples: `E2E-BAO-HO-LAO-DONG-2009-p13` `[0.4073720987654321, 0.09574985227392634, 0.6361104429920116, 0.10761966867152052]` IoU `0.00`; `E2E-BAO-HO-LAO-DONG-2009-p13` `[0.44495054103122733, 0.11948948506911469, 0.44603977124183003, 0.12067646670887412]` IoU `0.00`
- `title`: 7 FP. Examples: `E2E-BAO-HO-LAO-DONG-2009-p13` `[0.4106397893972404, 0.07834078822412155, 0.6306642919389978, 0.09060626516830221]` IoU `0.35`; `E2E-LONG-HAU-2008-p6` `[0.12655713112305855, 0.04314748746371074, 0.4132706317204301, 0.06175236737925574]` IoU `0.00`
- `figure`: 2 FP. Examples: `E2E-BAO-HO-LAO-DONG-2009-p24` `[0.3000475445064888, 0.9573596867365637, 0.42503306312018657, 0.9760755110252952]` IoU `0.45`; `E2E-LONG-HAU-2008-p8` `[0.1194892690963104, 0.7604525967052034, 0.382107441365218, 0.8547717749081429]` IoU `0.50`
- `page_furniture`: 13 FP. Examples: `E2E-BAO-HO-LAO-DONG-2009-p13` `[0.5794704720406681, 0.03679643083254194, 0.8871780065359477, 0.06370134800042207]` IoU `0.34`; `E2E-BAO-HO-LAO-DONG-2009-p13` `[0.15521530501089326, 0.9452330457950828, 0.8681164778503992, 0.9590811649256094]` IoU `0.47`
- Unclassified `other` boxes: 2

### doclayout-yolo-conf040

Source run: `layout-candidate-doclayout-yolo-20261030-conf04`; model: `DocLayout-YOLO DocStructBench`; device: `cpu`; confidence/score threshold: `0.4`.

| Label | TP / predicted / reference | Precision | Recall | F1 | False positives |
|---|---:|---:|---:|---:|---:|
| table | 5 / 5 / 5 | 100.0% | 100.0% | 100.0% | 0 |
| text | 1 / 9 / 6 | 11.1% | 16.7% | 13.3% | 8 |
| title | 2 / 5 / 9 | 40.0% | 22.2% | 28.6% | 3 |
| figure | 0 / 0 / 12 | 0.0% | 0.0% | 0.0% | 0 |
| page_furniture | 0 / 0 / 10 | 0.0% | 0.0% | 0.0% | 0 |

False positive summary (all coordinates and nearest IoU values are in `evaluation.json`):

- `text`: 8 FP. Examples: `E2E-BAO-HO-LAO-DONG-2009-p13` `[0.7544945012510212, 0.12369081618552648, 0.8888199550653595, 0.1373257107204861]` IoU `0.00`; `E2E-BAO-HO-LAO-DONG-2009-p24` `[0.14618854694538289, 0.17274372709690552, 0.8122892565159732, 0.1983979961382838]` IoU `0.00`
- `title`: 3 FP. Examples: `E2E-BAO-HO-LAO-DONG-2009-p24` `[0.143825641340868, 0.11486552980901364, 0.6146797625133357, 0.15819010284125612]` IoU `0.26`; `E2E-LONG-HAU-2008-p6` `[0.12433646827615717, 0.04123421712046281, 0.4168175317907846, 0.06245352774504528]` IoU `0.00`
- Unclassified `other` boxes: 0

### doclayout-yolo-conf025

Source run: `layout-candidate-doclayout-yolo-20261030`; model: `DocLayout-YOLO DocStructBench`; device: `cpu`; confidence/score threshold: `0.25`.

| Label | TP / predicted / reference | Precision | Recall | F1 | False positives |
|---|---:|---:|---:|---:|---:|
| table | 5 / 5 / 5 | 100.0% | 100.0% | 100.0% | 0 |
| text | 1 / 11 / 6 | 9.1% | 16.7% | 11.8% | 10 |
| title | 2 / 8 / 9 | 25.0% | 22.2% | 23.5% | 6 |
| figure | 0 / 0 / 12 | 0.0% | 0.0% | 0.0% | 0 |
| page_furniture | 0 / 0 / 10 | 0.0% | 0.0% | 0.0% | 0 |

False positive summary (all coordinates and nearest IoU values are in `evaluation.json`):

- `text`: 10 FP. Examples: `E2E-BAO-HO-LAO-DONG-2009-p13` `[0.7544945012510212, 0.12369081618552648, 0.8888199550653595, 0.1373257107204861]` IoU `0.00`; `E2E-BAO-HO-LAO-DONG-2009-p24` `[0.14618854694538289, 0.17274372709690552, 0.8122892565159732, 0.1983979961382838]` IoU `0.00`
- `title`: 6 FP. Examples: `E2E-BAO-HO-LAO-DONG-2009-p13` `[0.7544945012510212, 0.12369081618552648, 0.8888199550653595, 0.1373257107204861]` IoU `0.00`; `E2E-BAO-HO-LAO-DONG-2009-p24` `[0.143825641340868, 0.11486552980901364, 0.6146797625133357, 0.15819010284125612]` IoU `0.26`
- Unclassified `other` boxes: 0

### pp-doclayout-s-conf040

Source run: `layout-candidate-pp-doclayout-s-20261030`; model: `PP-DocLayout-S`; device: `cpu`; confidence/score threshold: `0.4`.

| Label | TP / predicted / reference | Precision | Recall | F1 | False positives |
|---|---:|---:|---:|---:|---:|
| table | 3 / 3 / 5 | 100.0% | 60.0% | 75.0% | 0 |
| text | 3 / 19 / 6 | 15.8% | 50.0% | 24.0% | 16 |
| title | 1 / 2 / 9 | 50.0% | 11.1% | 18.2% | 1 |
| figure | 1 / 3 / 12 | 33.3% | 8.3% | 13.3% | 2 |
| page_furniture | 0 / 6 / 10 | 0.0% | 0.0% | 0.0% | 6 |

False positive summary (all coordinates and nearest IoU values are in `evaluation.json`):

- `text`: 16 FP. Examples: `E2E-BAO-HO-LAO-DONG-2009-p13` `[0.9648465424581291, 0.5832661540872804, 0.983932435278799, 0.6990705962873932]` IoU `0.00`; `E2E-BAO-HO-LAO-DONG-2009-p13` `[0, 0.5191138576351793, 0.0365330415613511, 0.9817381421385327]` IoU `0.00`
- `title`: 1 FP. Examples: `E2E-BAO-HO-LAO-DONG-2009-p13` `[0.7554550270629085, 0.12330130407726436, 0.8895386540032679, 0.13562604391563537]` IoU `0.00`
- `figure`: 2 FP. Examples: `E2E-BAO-HO-LAO-DONG-2009-p24` `[0.1604022428061285, 0.3091984553135179, 0.9153465245673305, 0.7495803485087541]` IoU `0.00`; `E2E-LONG-HAU-2008-p8` `[0.5304539998372396, 0.7475902566434085, 0.7012808194724462, 0.8691435825230107]` IoU `0.49`
- `page_furniture`: 6 FP. Examples: `E2E-BAO-HO-LAO-DONG-2009-p13` `[0.7158535826439951, 0.036276503053033, 0.8888774797028186, 0.04792252021637398]` IoU `0.08`; `E2E-LONG-HAU-2008-p6` `[0.8120184457430275, 0.04639840748984004, 0.8741535473895329, 0.057691205312407214]` IoU `0.04`
- Unclassified `other` boxes: 0

### egret-medium

Source run: `docling-pilot-5-egret-layout-20261029`; model: `Layout egret-medium`; device: `CPU`; confidence/score threshold: `not recorded`.

| Label | TP / predicted / reference | Precision | Recall | F1 | False positives |
|---|---:|---:|---:|---:|---:|
| table | 5 / 5 / 5 | 100.0% | 100.0% | 100.0% | 0 |
| text | 3 / 107 / 6 | 2.8% | 50.0% | 5.3% | 104 |
| title | 0 / 4 / 9 | 0.0% | 0.0% | 0.0% | 4 |
| figure | 2 / 3 / 12 | 66.7% | 16.7% | 26.7% | 1 |
| page_furniture | 1 / 15 / 10 | 6.7% | 10.0% | 8.0% | 14 |

False positive summary (all coordinates and nearest IoU values are in `evaluation.json`):

- `text`: 104 FP. Examples: `E2E-BAO-HO-LAO-DONG-2009-p13` `[0.15793838053740014, 0.04945756832330907, 0.421532091503268, 0.06488832964018149]` IoU `0.00`; `E2E-BAO-HO-LAO-DONG-2009-p13` `[0.4073720987654321, 0.09574985227392634, 0.6361104429920116, 0.10761966867152052]` IoU `0.00`
- `title`: 4 FP. Examples: `E2E-BAO-HO-LAO-DONG-2009-p13` `[0.4106397893972404, 0.07834078822412155, 0.6306642919389978, 0.09060626516830221]` IoU `0.35`; `E2E-LONG-HAU-2008-p6` `[0.12655713112305855, 0.04314748746371074, 0.4132706317204301, 0.06175236737925574]` IoU `0.00`
- `figure`: 1 FP. Examples: `E2E-LONG-HAU-2008-p8` `[0.18670304242302393, 0.7603527078152837, 0.24755892713530725, 0.8082001384816658]` IoU `0.14`
- `page_furniture`: 14 FP. Examples: `E2E-BAO-HO-LAO-DONG-2009-p13` `[0.002178460421205519, 0.02215699060884246, 0.033221521423384165, 0.9662030547641658]` IoU `0.00`; `E2E-BAO-HO-LAO-DONG-2009-p13` `[0.15848299564270152, 0.03521378864619605, 0.5914520043572985, 0.04985322886989554]` IoU `0.26`
- Unclassified `other` boxes: 1
