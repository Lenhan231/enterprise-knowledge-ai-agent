# Parser chunking

`ChunkingProcessor` converts normalized parser elements and structured tables
into the parser chunks that Upload Test displays and production persists in
`document_parser_chunks`. It does not tokenize or embed them.

## Text chunks

Sentence mode is the default. It groups paragraph and sentence boundaries up
to the configured character ceiling. Fixed mode makes overlapping character
windows for comparison. The current defaults are 1,100 characters and 120
characters of overlap; sentence mode does not use overlap. Size, strategy, and
actual character count are recorded in chunk metadata.

## Table chunks

Tables stay structured in parser output and also produce row-aware text chunks.
Each fragment repeats the section context, table title, and column headers;
rows remain whole. The metadata records table identity and row ranges so a
chunk can be traced to its source table.

## Code path and configuration

- `chunking/processor.py` orders text and table chunks from parser output.
- `chunking/text/` contains the fixed and sentence strategies.
- `chunking/table/chunker.py` groups structured rows into chunks.
- `chunking/config.py` owns shared character size, overlap, and strategy.
- Uploads read `DOCUMENT_CHUNKING_STRATEGY` (`sentence` by default; `fixed` is
  the comparison option).

The parser-chunk output is the end of this module's responsibility. Model-
specific token limits and retrieval indexing are handled downstream.

## Module Docker image

Build from the repository root:

```sh
docker build -f docker/Dockerfile.chunking -t chunking .
docker run --rm chunking
```

This image contains only `core/chunking` and Python. The module uses the
standard library, so no model or third-party dependency is installed.
The default command chunks sample text; success prints
`PASS: core.chunking smoke check` and exits with code 0.

Override the command to run your own script against saved parser JSON:

```sh
docker run --rm -v "$PWD:/work" chunking python /work/your_script.py
```

The script loads the JSON and calls `ChunkingProcessor().process(parsed)`.
This image has no HTTP server or exposed port.
