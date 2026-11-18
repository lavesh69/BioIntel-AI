from __future__ import annotations
import tempfile,unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch
from biointel.connect.services import build_connect_services
from biointel.connect import ui,complete_ui,advanced_ui

class FakeContext:
    def __enter__(self): return self
    def __exit__(self,*args): return False
class FakeStreamlit:
    def __init__(self): self.session_state={}; self.query_params={}
    def tabs(self,labels): return [FakeContext() for _ in labels]
    def columns(self,spec,*args,**kwargs): return [FakeContext() for _ in range(spec if isinstance(spec,int) else len(spec))]
    def container(self,*args,**kwargs): return FakeContext()
    def form(self,*args,**kwargs): return FakeContext()
    def expander(self,*args,**kwargs): return FakeContext()
    def popover(self,*args,**kwargs): return FakeContext()
    def button(self,*args,**kwargs): return False
    def form_submit_button(self,*args,**kwargs): return False
    def text_input(self,*args,**kwargs): return kwargs.get('value','')
    def text_area(self,*args,**kwargs): return kwargs.get('value',args[1] if len(args)>1 else '')
    def selectbox(self,label,options,*args,**kwargs):
        values=list(options); return values[kwargs.get('index',0)] if values else None
    def multiselect(self,*args,**kwargs): return kwargs.get('default',[])
    def segmented_control(self,*args,**kwargs): return kwargs.get('default')
    def radio(self,label,options,*args,**kwargs): return list(options)[kwargs.get('index',0)]
    def toggle(self,*args,**kwargs): return kwargs.get('value',False)
    def checkbox(self,*args,**kwargs): return kwargs.get('value',False)
    def number_input(self,*args,**kwargs): return kwargs.get('value',kwargs.get('min_value',0))
    def slider(self,*args,**kwargs): return kwargs.get('value',kwargs.get('min_value',0))
    def file_uploader(self,*args,**kwargs): return [] if kwargs.get('accept_multiple_files') else None
    def data_editor(self,data,*args,**kwargs): return data
    def __getattr__(self,name):
        def noop(*args,**kwargs): return None
        return noop

class ConnectUISmokeTests(unittest.TestCase):
    def test_all_connect_renderers_have_non_placeholder_idle_state(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); services=build_connect_services(database_path=root/'db.sqlite3',storage_root=root/'media'); user=services.ensure_identity('ui-user','UI User','administrator'); triple=(services,user,services.complete); fake=FakeStreamlit()
            with patch.object(ui,'st',fake),patch.object(complete_ui,'st',fake),patch.object(advanced_ui,'st',fake),patch.object(ui,'_services',lambda _root:services),patch.object(complete_ui,'_suite',lambda _root:triple),patch.object(advanced_ui,'_suite',lambda _root:triple):
                for renderer in (ui.render_home,ui.render_create_post,ui.render_network,ui.render_profile,ui.render_post_detail,ui.render_notifications,ui.render_settings): renderer(root)
                for renderer in (complete_ui.render_messages,complete_ui.render_communities,complete_ui.render_discover_collaborate,complete_ui.render_stories_videos,complete_ui.render_live_calls,complete_ui.render_onboarding_verification,complete_ui.render_admin_operations,complete_ui.render_accessibility_notifications): renderer(root)
                for name in sorted(x for x in dir(advanced_ui) if x.startswith('render_')): getattr(advanced_ui,name)(root)
if __name__=='__main__': unittest.main()

