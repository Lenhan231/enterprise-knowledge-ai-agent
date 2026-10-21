"""Main parser -> shared chunker -> Huy token provenance, without model/DB writes."""
import asyncio
import hashlib
import inspect
import io
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock,patch
import zipfile

import fitz
from fastapi import UploadFile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from core.document_processing.document_processor import DocumentProcessor
from core.document_processing.chunking.processor import ChunkingProcessor
from core.document_processing.readers.image.processor import ScannedImageProcessor
from core.tokenization.embedding_chunker import build_embedding_chunks
from core.tokenization.token_counter import TokenCounter


def office(files):
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w') as z:
        for name,text in files.items():z.writestr(name,text)
    return output.getvalue()


def docx():
    return office({'word/document.xml':'''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
<w:p><w:r><w:t>Before table evidence.</w:t></w:r></w:p>
<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Field</w:t></w:r></w:p></w:tc></w:tr>
<w:tr><w:tc><w:p><w:r><w:t>Table evidence</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
<w:p><w:r><w:t>After table evidence.</w:t></w:r></w:p></w:body></w:document>'''})


class CharacterTokenizer:
    def num_special_tokens_to_add(self,pair=False):return 2
    def encode(self,text,add_special_tokens=False):return list(text)
    def __call__(self,text,**kwargs):return {'offset_mapping':[(i,i+1) for i in range(len(text))]}


def counter():
    value=TokenCounter.__new__(TokenCounter);value.tokenizer=CharacterTokenizer();return value


def processed(name,content,metadata=None,config=None):
    parser=DocumentProcessor(config);parsed=parser.process(name,content,metadata or {})
    return parsed,ChunkingProcessor(parser.config).process(parsed)


class ParserChunkingIntegrationTest(unittest.TestCase):
    def test_docx_table_stays_between_prose_and_stage_contract_is_explicit(self):
        raw,out=processed('order.docx',docx(),{'document_id':'DOC-ORDER','allowed_roles':['employee']})
        self.assertNotIn('chunks',raw)
        self.assertEqual([e['metadata']['element_type'] for e in raw['elements']],['text','table','text'])
        chunks=out['chunks'];self.assertEqual(len(chunks),3)
        self.assertEqual(chunks[0]['text'],'Before table evidence.')
        self.assertIn('Field: Table evidence',chunks[1]['text'])
        self.assertEqual(chunks[2]['text'],'After table evidence.')
        self.assertEqual([c['metadata']['chunk_index'] for c in chunks],[0,1,2])
        for c in chunks:
            self.assertEqual(c['metadata']['document_id'],'DOC-ORDER')
            self.assertEqual(c['metadata']['allowed_roles'],['employee'])
        self.assertEqual(chunks[1]['metadata']['layout_type'],'table')
        self.assertEqual(chunks[1]['metadata']['paragraph_index'],1)

    def test_heading_with_body_does_not_drop_first_fact(self):
        source='# Policy\nUNIQUE_FIRST_FACT. '+'Subsequent sentence with other content. '*15
        _,out=processed('policy.md',source.encode(),config={'chunk_size':100,'chunk_overlap':0})
        self.assertGreater(len(out['chunks']),1)
        self.assertIn('UNIQUE_FIRST_FACT.',' '.join(c['text'] for c in out['chunks']))
        self.assertEqual(sum(c['text'].count('Subsequent sentence with other content.') for c in out['chunks']),15)
        self.assertTrue(all(c['metadata']['section_title']=='Policy' for c in out['chunks']))

    def test_table_data_reference_from_optional_pipeline_is_normalized(self):
        for representation in ('table_ref','table_data'):
            with self.subTest(representation=representation):
                table={'columns':['SKU'],'rows':[{'SKU':'A1'}],'metadata':{}}
                element={'element_type':'table','metadata':{'element_type':'paragraph','layout_type':'text'}}
                if representation=='table_ref':element['table_ref']=0;tables=[table]
                else:element['table_data']=table;tables=[]
                payload={'elements':[element],'tables':tables}
                with patch('core.document_processing.document_processor.process_docling',return_value=payload):
                    raw,out=processed('table.pdf',b'fixture',{'document_id':'DOC-TABLE'},{'parser_engine':'docling'})
                self.assertEqual(raw['elements'][0]['metadata']['layout_type'],'table')
                self.assertEqual(len(out['chunks']),1)
                self.assertIn('SKU: A1',out['chunks'][0]['text'])

    def test_xlsx_sheet_and_csv_table_metadata_reach_chunks(self):
        source=office({
            'xl/workbook.xml':'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="README" sheetId="1" r:id="rId1"/></sheets></workbook>',
            'xl/_rels/workbook.xml.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',
            'xl/worksheets/sheet1.xml':'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Rule</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>Three snapshots</t></is></c></row></sheetData></worksheet>'})
        for name,data in [('book.xlsx',source),('rules.csv',b'Rule\nThree snapshots\n')]:
            with self.subTest(name=name):
                _,out=processed(name,data)
                self.assertEqual(out['chunks'][0]['metadata']['element_type'],'table')
                self.assertIn('Three snapshots',out['chunks'][0]['text'])
                if name.endswith('xlsx'):self.assertEqual(out['chunks'][0]['metadata']['sheet_name'],'README')

    def test_native_pdf_pages_and_mocked_ocr_image_keep_locations(self):
        pdf=fitz.open()
        for number in (1,2):
            page=pdf.new_page();page.insert_text((40,60),f'Page {number} inventory evidence and independent approval rules.',fontsize=11)
        source=pdf.tobytes();pdf.close()
        _,out=processed('native.pdf',source,config={'ocr_fallback':False})
        self.assertEqual({c['metadata']['page_number'] for c in out['chunks']},{1,2})
        with patch.object(ScannedImageProcessor,'_ocr',return_value='Inventory evidence from OCR.'):
            _,out=processed('scan.png',b'image fixture',{'document_id':'IMAGE'})
        self.assertEqual(out['chunks'][0]['metadata']['document_id'],'IMAGE')
        self.assertIsNone(out['chunks'][0]['metadata'].get('page_number'))

    def test_bounded_passages_keep_exact_source_coordinates_and_access(self):
        _,parsed=processed('long.md',('# Policy\n'+'Evidence fact with useful words. '*30).encode(),{'document_id':'DOC-MAP','allowed_roles':['employee']})
        parents=parsed['chunks'];bounded=build_embedding_chunks(parents,counter(),96,'fixture-tokenizer')
        covered={i:set() for i in range(len(parents))}
        self.assertGreater(len(bounded),len(parents))
        for c in bounded:
            m=c['metadata'];i=m['source_parser_index'];parent=parents[i]['text']
            self.assertEqual(m['source_content_sha256'],hashlib.sha256(parent.encode()).hexdigest())
            self.assertEqual(m['allowed_roles'],['employee']);self.assertEqual(m['document_id'],'DOC-MAP')
            self.assertLessEqual(m['token_count'],94)
            for span in m['source_spans']:
                a,b=span['source_start'],span['source_end'];x,y=span['chunk_start'],span['chunk_end']
                self.assertEqual(parent[a:b],c['text'][x:y]);covered[i].update(range(a,b))
        for i,p in enumerate(parents):self.assertTrue(all(ch.isspace() or n in covered[i] for n,ch in enumerate(p['text'])))

    def test_production_upload_persists_parser_order_and_token_provenance(self):
        from app import main
        storage=MagicMock();parsed_repo=MagicMock();chunk_repo=MagicMock();embedding=MagicMock()
        embedding.model_name='fixture-tokenizer';embedding.max_sequence_length=96
        embedding.embed_documents.side_effect=lambda texts:[[.1,.2,.3] for text in texts]
        with (patch.object(main,'_require_same_origin'),patch.object(main,'_storage_client',return_value=(storage,'private')),
              patch.object(main,'DocumentRepository'),patch('core.database.parser_chunks_repository.ParserChunksRepository',return_value=parsed_repo),
              patch('core.database.structured_store.StructuredDataStore'),patch('core.database.document_chunks_repository.DocumentChunkRepository',return_value=chunk_repo),
              patch('core.embeddings.embedding_service.EmbeddingService',return_value=embedding),patch('core.tokenization.token_counter.TokenCounter',return_value=counter())):
            result=asyncio.run(main.upload_document(request=SimpleNamespace(url=SimpleNamespace(path='/api/documents/upload')),
                file=UploadFile(filename='order.docx',file=io.BytesIO(docx())),title='Order',document_type='knowledge_document',
                domain='general',fiscal_year=None,source_url=None,allowed_roles=['employee'],ocr_language='eng',user={'sub':'test','role':'admin'}))
        self.assertEqual(result['processing_status'],'ready');self.assertEqual(result['parser_chunk_count'],3)
        saved=parsed_repo.replace_document.call_args.args[1]
        self.assertEqual([c['metadata']['element_type'] for c in saved],['text','table','text'])
        indexed=chunk_repo.replace_document.call_args.args[1]
        self.assertEqual([c[3]['source_parser_index'] for c in indexed],[0,1,2])
        self.assertTrue(all(c[3]['allowed_roles']==['employee'] for c in indexed))

    def test_upload_test_uses_shared_chunker_and_preserves_response_contract(self):
        from app import upload_test
        defaults={name:getattr(p.default,'default',p.default) for name,p in inspect.signature(upload_test.create_upload_test).parameters.items() if p.default is not inspect.Parameter.empty}
        defaults.update(request=None,file=UploadFile(filename='order.docx',file=io.BytesIO(docx())),user={'sub':'test'})
        repo=MagicMock()
        with (patch.object(upload_test,'_require_same_origin'),patch.object(upload_test.subprocess,'run',return_value=SimpleNamespace(stdout='tesseract fixture')),
              patch('core.database.upload_test_repository.UploadTestRepository',return_value=repo)):
            response=asyncio.run(upload_test.create_upload_test(**defaults))
        saved=repo.save_run.call_args.kwargs
        self.assertEqual([c['metadata']['element_type'] for c in saved['chunks']],['text','table','text'])
        self.assertEqual(response['embedding_status'],'not_run');self.assertIsNone(response['embedding_error'])
        self.assertEqual(saved['embeddings'],[])

if __name__=='__main__':unittest.main()