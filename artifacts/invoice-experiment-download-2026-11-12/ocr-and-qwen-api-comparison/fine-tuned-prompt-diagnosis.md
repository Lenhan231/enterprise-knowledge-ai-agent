# Fine-tuned Qwen3-0.6B prompt diagnosis

## Evidence

The benchmark used 50 invoices, one shared OCR result set from `lenhanm1/enterprise-printed-ocr-vietocr-tesseract` revision `6deb1cb10ecbf240aead77525e80aa4c58adfb23`, and the production extraction prompt. Dates are scored equal when the only difference is a leading Vietnamese `Ngày` label.

Fine-tuned Qwen3-0.6B produced valid schema output for 50/50 invoices, but only 5/50 were whole-invoice exact (10%). Item-row exact accuracy was 96.1%, so most of the gap comes from header fields rather than table extraction.

- `invoice_no` was wrong on 39/50 invoices. The OCR contains the correct invoice identifier, but the model often selected another value: a party identifier (26 cases returned the tax identifier, with or without its label), a title, an amount, or a party name.
- `subtotal` was wrong on 15/50 invoices. In every one of those cases the model copied the predicted `total_amount` into `subtotal`, although OCR showed separate pre-tax subtotal and payable-total values.
- Seller/buyer errors affected 3 invoices combined; tax and total each affected one. Item-field errors were much less frequent.
- On the same OCR evidence, base Qwen3-1.7B extracted invoice numbers correctly on 50/50 and Gemini 3.5 Flash-Lite on 50/50. This supports a model instruction-following/field-association weakness in the fine-tuned 0.6B model, rather than missing OCR evidence as the main cause.

The prompt already mentioned invoice-number labels and subtotal/tax/total distinctions, but the fine-tuned model frequently ignored those instructions. This is evidence of weak semantic association and instruction adherence; prompt changes alone are not yet proven to improve accuracy.

## Prompt adjustment

The shared extraction instructions now require every value to be tied to the field through its label, document meaning, party role, or table row/column. They reject selection by number shape or usual position, require value-only output, and prefer null when the relationship is unclear. Header guidance distinguishes the invoice's own identifier from party and other document identifiers, and keeps subtotal, tax, and payable total semantically separate. Table guidance says column order can vary and treats `source_row` as alignment metadata rather than invoice content.

The revised prompt does not depend on fixed OCR strings, coordinates, table layouts, or invoice-specific numeric examples. The 50-invoice benchmark has not yet been rerun with this prompt.
