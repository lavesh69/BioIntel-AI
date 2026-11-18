from __future__ import annotations
import tempfile,unittest
from pathlib import Path
from biointel.connect.services import build_connect_services
from biointel.connect.phase_c import GrantIntelligenceService
from biointel.connect.phase_d import PreprintPublishingService
from biointel.connect.phase_e import KnowledgeGraphService
from biointel.connect.phase_f import EquipmentBookingService
class AdvancedPersistenceTests(unittest.TestCase):
    def test_phase_c_to_f_resources_survive_restart(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); db=root/'db.sqlite3'; media=root/'media'; first=build_connect_services(database_path=db,storage_root=media); user=first.ensure_identity('user','User'); grant=GrantIntelligenceService(first).add_opportunity('Sponsor','Grant',1.0,'2030-01-01',['omics']); preprint=PreprintPublishingService(first).submit_preprint(user['user_id'],'Title','Abstract'); graph=KnowledgeGraphService(first); graph.add_node('gene_tp53','TP53','gene'); equipment=EquipmentBookingService(first).register_equipment(user['user_id'],'Microscope','Lab')
            second=build_connect_services(database_path=db,storage_root=media); self.assertIn(grant['grant_id'],GrantIntelligenceService(second)._opportunities); self.assertIn(preprint['preprint_id'],PreprintPublishingService(second)._preprints); self.assertIn('gene_tp53',KnowledgeGraphService(second)._nodes); self.assertIn(equipment['equipment_id'],EquipmentBookingService(second)._equipment)
if __name__=='__main__': unittest.main()
