# New document test inputs

- [VietStyle Vietnamese policy](vietstyle-operations-vi-v1/README.md): translation of the user's English policy; 54 physical PDF pages including50 numbered policy pages, front matter and appendices. Editable DOCX and PDF included. This is a separate policy with its own rules, not a renamed Bảo An handbook.
- [Bảo An synthetic handbook](bao-an-operations-vi-v1/README.md): exactly50 pages,48 digital +2 image-only, with30 draft bilingual evaluation intents. Labels require independent review.

The user-created `vietstyle-operations-vi-v1.zip` here packages the VietStyle folder. `../datasets.zip` packages only the Bảo An folder. Both archives were compared to the unpacked files before this checkpoint; use the folders as the working copies.

Neither new document has benchmark results yet. They do not replace the80-case Review2 result. Keep questions, answers, alignment/authoring files and scan transcriptions out of the PDF search index. Use existing retrieval results for the slides; run an unchanged baseline on reviewed new inputs before any later tuning.

Generator source files are in scripts/evaluation/. Hash-sensitive dataset and generator files retain their bytes across Windows and WSL checkouts. Vietnamese translation rebuilding needs the original downloaded English DOCX, which is not part of this checkpoint; the final Vietnamese DOCX/PDF are included and can be used directly on the PC.
