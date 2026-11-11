import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from streamlit.testing.v1 import AppTest
from core.agents import streamlit_ui as ui


def response(value):
    return {'answer':f'Stock is {value}','agent':'analytics','data':{'sql':'SELECT i.stock_on_hand FROM commerce.inventory AS i LIMIT 1',
            'parameters':[],'query_status':'executed','rows':[{'stock_on_hand':value}]},'metadata':{}}


class SessionChatTest(unittest.TestCase):
    @patch.dict(os.environ,{'API_AGENT_PREFIX':'/api'})
    def test_reports_stay_separate_and_reset_clears_download_and_draft(self):
        app=self.app()
        with patch.object(ui,'submit_chat',return_value=response(1)):
            app.chat_input[0].set_value('Chat question').run()
        app.selectbox[0].select('Report').run()
        self.assertEqual(len(app.chat_input),0)
        app.text_area[0].set_value('Make report').run()
        with patch.object(ui,'submit_report',return_value=(b'# Report','text/markdown','complete')):
            next(b for b in app.button if b.label=='Generate report').click().run()
        self.assertIn('report_download',app.session_state)
        self.assertEqual(len(app.session_state['chat_turns']),1)
        app.button(key='new_conversation').click().run()
        self.assertNotIn('report_download',app.session_state)
        self.assertEqual(app.text_area[0].value,'')
        self.assertEqual(app.session_state['chat_turns'],[])
        self.assertFalse(app.exception)

    @patch.dict(os.environ,{'API_AGENT_PREFIX':'/api'})
    def test_dashboard_history_renders_repeated_charts_and_context_caption(self):
        payload={'answer':'Dashboard','data':{'dashboard':{'outline_id':'inventory_control','snapshot_date':'2022-12-31',
            'kpis':{'sku_count':1,'mean_fill_rate':.9},'stockout_by_category':[{'category':'A','stockout_rate':1}],
            'inventory_flags':[{'category':'A','stockout_flag_count':1,'overstock_flag_count':0,'both_flags_count':0}]}},
            'metadata':{'context_used':True,'semantic_interpretation':{'time':{'mode':'snapshot','start':'2022-12-31'},
                      'filters':[{'field':'color','operator':'eq','value':'blue'}]}}}
        app=self.app()
        with patch.object(ui,'submit_chat',return_value=payload):
            app.chat_input[0].set_value('Dashboard').run()
            app.chat_input[0].set_value('Dashboard again').run()
        self.assertEqual(len(app.chat_message),4)
        self.assertTrue(any('2022-12-31' in c.value for c in app.caption))
        self.assertTrue(any('blue' in c.value for c in app.caption))
        self.assertFalse(app.exception)

    def app(self):
        return AppTest.from_string('from core.agents.streamlit_ui import main\nmain()',default_timeout=10).run()

    @patch.dict(os.environ,{'API_AGENT_PREFIX':'/api'})
    def test_transcript_keeps_results_without_resubmission_and_unique_downloads(self):
        with patch.object(ui,'submit_chat',side_effect=[response(3),response(5)]) as submit:
            app=self.app()
            app.chat_input[0].set_value('First question').run()
            app.chat_input[0].set_value('Second question').run()
            self.assertEqual(len(app.chat_message),4)
            self.assertEqual(len(app.dataframe),2)
            self.assertEqual(len(app.get('download_button')),2)
            app.run()
            self.assertEqual(submit.call_count,2)
            self.assertFalse(app.exception)
            app.selectbox[0].select('Knowledge').run()
            self.assertEqual(len(app.chat_message),4)
            app.button(key='new_conversation').click().run()
            self.assertEqual(len(app.chat_message),0)
            self.assertEqual(app.selectbox[0].value,'Knowledge')

    @patch.dict(os.environ,{'API_AGENT_PREFIX':'/api'})
    def test_twenty_exchange_limit_and_error_turn(self):
        with patch.object(ui,'submit_chat',return_value=response(1)):
            app=self.app()
            for n in range(21):app.chat_input[0].set_value(f'Question {n}').run()
            self.assertEqual(len(app.chat_message),40)
            self.assertEqual(len(app.session_state['chat_turns']),20)
        with patch.object(ui,'submit_chat',side_effect=RuntimeError('Backend unavailable')):
            app.chat_input[0].set_value('Failed question').run()
            self.assertIn('Backend unavailable',[e.value for e in app.error])
            self.assertEqual(len(app.chat_message),40)

    @patch.dict(os.environ,{'API_AGENT_PREFIX':'/api'})
    def test_late_response_after_reset_is_discarded(self):
        app=self.app()
        def late(*args,**kwargs):
            app.session_state['conversation_id']='reset-during-request'
            return response(99)
        with patch.object(ui,'submit_chat',side_effect=late):
            app.chat_input[0].set_value('Old question').run()
        self.assertEqual(app.session_state['chat_turns'],[])
        self.assertFalse(app.exception)

    @patch.dict(os.environ,{'API_AGENT_PREFIX':'/api/agents'})
    def test_signout_clears_chat_and_report_state(self):
        app=self.app()
        app.session_state['api_opener']=Mock()
        app.session_state['chat_turns']=[{'id':'old','question':'Private','mode':'SQL','result':response(1)}]
        app.session_state['report_download']=(b'old','text/markdown','complete')
        app.run()
        app.button(key='sign_out').click().run()
        self.assertNotIn('api_opener',app.session_state)
        self.assertNotIn('chat_turns',app.session_state)
        self.assertNotIn('report_download',app.session_state)
        self.assertEqual([x.label for x in app.text_input],['Username','Password'])
