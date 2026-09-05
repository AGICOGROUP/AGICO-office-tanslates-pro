from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from translation_batches import export_batches, merge_results


class TranslationBatchTests(unittest.TestCase):
    def test_ppt_prepare_exports_pending_work_without_geometry_or_occurrence_copies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            item={'id':'slide:1/shape:2/paragraph:1','source_text':'设备','role':'title','context_signature':'title','protected_tokens':[], 'slide_index':1,'shape_id':2,'paragraph_index':1}
            inventory={'source_file':'source.pptx','source_sha256':'a'*64,'occurrences':[item],'image_groups':[]}
            (root/'inventory.json').write_text(json.dumps(inventory),encoding='utf-8')
            (root/'job-state.json').write_text(json.dumps({'target_language':'en','stages':{}}),encoding='utf-8')
            run=subprocess.run([sys.executable,str(ROOT/'formats/ppt/scripts/ppt_pipeline.py'),'prepare','--job-dir',str(root)],capture_output=True)
            self.assertEqual(run.returncode,3,run.stderr)
            index=json.loads((root/'translation-worklist.json').read_text(encoding='utf-8'))
            batch=json.loads((root/index['batches'][0]['file']).read_text(encoding='utf-8'))
            self.assertEqual(batch['items'][0]['source'],'设备')
            self.assertEqual(batch['items'][0]['role'],'title')
            self.assertNotIn('occurrences',batch)

    def test_prepare_does_not_destroy_existing_translation_work(self):
        for kind, script, extra in [
            ('word','word_pipeline.py',['unused.docx','--target-language','en']),
            ('ppt','ppt_pipeline.py',[]),
            ('excel','excel_fast_pipeline.py',['--source','unused.xlsx','--target-language','en','--output-mode','monolingual'])]:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); path=self.setup_job(root)
                before=path.read_bytes()
                run=subprocess.run([sys.executable,str(ROOT/'formats'/kind/'scripts'/script),'prepare','--job-dir',str(root),*extra],capture_output=True)
                self.assertEqual(run.returncode,2)
                self.assertIn(b'already prepared',run.stdout+run.stderr)
                self.assertEqual(path.read_bytes(),before)

    def test_introduced_word_separator_and_completed_correction_have_retry_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.setup_job(Path(tmp)); index=export_batches(path,kind='word')
            self.submit(path,index['job_id'],[{'id':1,'translation':'Title'}])
            report=self.submit(path,index['job_id'],[{'id':1,'translation':'New\tTitle','previous_translation':'Title'}])
            self.assertTrue(report['errors'])
            retry=json.loads((path.parent/report['retry_index']).read_text(encoding='utf-8'))
            batch=json.loads((path.parent/retry['batches'][0]['file']).read_text(encoding='utf-8'))
            self.assertEqual(batch['items'][0]['id'],1)

    def test_adapter_corrections_invalidate_old_delivery_state(self):
        for kind, script in [('excel', 'excel_fast_pipeline.py'), ('ppt', 'ppt_pipeline.py')]:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); manifest=self.setup_job(root,'excel')
                data=json.loads(manifest.read_text(encoding='utf-8'))
                if kind=='ppt':
                    for unit in data['translation_units']:
                        unit['source_text']=unit.pop('source')
                    state={'stages':{s:{'completed':True,'artifact':'old'} for s in ['prepare','translate','validate','apply','verify','render','deliver']}}
                    manifest.write_text(json.dumps(data),encoding='utf-8')
                    path=manifest
                else:
                    state={'completedStages':['preflight','inspect','prepare','translate','validate','apply','verify','office-validate'], 'stageArtifacts':{'apply':{'output':'old'}}}
                    path=root/'translation-worklist.json'
                    path.write_text(json.dumps(data),encoding='utf-8')
                (root/'job-state.json').write_text(json.dumps(state),encoding='utf-8')
                index=export_batches(path,kind=kind)
                response=root/'response.json'
                response.write_text(json.dumps({'job_id':index['job_id'],'translations':[{'id':'1','translation':'Title'}]}),encoding='utf-8')
                run=subprocess.run([sys.executable,str(ROOT/'formats'/kind/'scripts'/script),'merge','--job-dir',str(root),'--responses',str(response)],capture_output=True)
                self.assertEqual(run.returncode,0,run.stderr)
                current=json.loads((root/'job-state.json').read_text(encoding='utf-8'))
                if kind=='ppt':
                    self.assertFalse(current['stages']['render']['completed'])
                    self.assertFalse(json.loads((root/'verification.json').read_text())['passed'])
                else:
                    self.assertEqual(current['completedStages'],['preflight','inspect','prepare'])
                    self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['translation_units'][0]['status'],'translated')

    def test_character_limit_never_splits_a_paragraph_and_empty_resume_has_no_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.setup_job(Path(tmp))
            index=export_batches(path,kind='word',max_chars=1)
            self.assertEqual(len(index['batches']),3)
            self.submit(path,index['job_id'],[{'id':1,'translation':'Title'},{'id':2,'translation':'Power 75kW'},{'id':3,'translation':'A\tB'}])
            self.assertEqual(export_batches(path,kind='word')['batches'],[])
            retry=export_batches(path,kind='word',ids=['2'])
            batch=json.loads((path.parent/retry['batches'][0]['file']).read_text(encoding='utf-8'))
            self.assertEqual(batch['items'][0]['previous_translation'],'Power 75kW')

    def setup_job(self, root, kind='word'):
        units = [dict(id=i, source=s, target='') for i, s in enumerate(['标题', '功率75kW', '甲\t乙'], 1)]
        data = dict(source_sha256='a' * 64, target_language='en', units=units,
                    protected_tokens=[], baseline={'media_count': 2})
        if kind != 'word':
            data.pop('units')
            data['translation_units'] = [dict(id=str(u['id']), source=u['source'], translation='',
                status='pending', context_key='equipment', protected_tokens=['75kW'] if u['id']==2 else []) for u in units]
            data['images'] = [{'id': 'image', 'status': 'manual-review'}]
        path = root / 'translation-manifest.json'
        path.write_text(json.dumps(data), encoding='utf-8')
        return path

    def submit(self, path, job_id, translations):
        response = path.parent / 'response.json'
        response.write_text(json.dumps(dict(job_id=job_id, translations=translations)), encoding='utf-8')
        return merge_results(path, response, kind='word')

    def test_partial_merge_preserves_completed_and_retries_only_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.setup_job(Path(tmp))
            index = export_batches(path, kind='word', max_items=2)
            self.assertEqual(index['pending_count'], 3)
            self.assertEqual(len(index['batches']), 2)
            batch = json.loads((path.parent / index['batches'][0]['file']).read_text(encoding='utf-8'))
            self.assertNotIn('baseline', batch)
            self.assertEqual(batch['context_after'], '甲\t乙')
            report = self.submit(path, index['job_id'], [{'id': 1, 'translation':'Title'}, {'id':3, 'translation':'A B'}])
            self.assertEqual(report['accepted_ids'], [1])
            self.assertEqual(report['errors'][0]['id'], 3)
            retry = export_batches(path, kind='word')
            self.assertEqual(retry['pending_count'], 2)
            self.assertEqual(retry['job_id'], index['job_id'])
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['units'][0]['target'], 'Title')

    def test_stale_duplicate_unknown_responses_never_mutate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.setup_job(Path(tmp)); index=export_batches(path, kind='word')
            before=path.read_bytes()
            for job_id, items in [('wrong',[{'id':1,'translation':'Title'}]),
                (index['job_id'],[{'id':1,'translation':'Title'}]*2),
                (index['job_id'],[{'id':99,'translation':'Title'}])]:
                with self.assertRaises(ValueError): self.submit(path,job_id,items)
                self.assertEqual(path.read_bytes(),before)

    def test_correction_requires_matching_previous_translation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.setup_job(Path(tmp)); index=export_batches(path,kind='word')
            self.submit(path,index['job_id'],[{'id':1,'translation':'Title'}])
            result=self.submit(path,index['job_id'],[{'id':1,'translation':'Heading'}])
            self.assertTrue(result['errors'])
            result=self.submit(path,index['job_id'],[{'id':1,'translation':'Heading','previous_translation':'Title'}])
            self.assertFalse(result['errors'])

    def test_excel_keeps_images_and_context_and_checks_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.setup_job(Path(tmp),'excel'); original=json.loads(path.read_text())
            index=export_batches(path,kind='excel')
            response=path.parent/'response.json'
            response.write_text(json.dumps({'job_id':index['job_id'],'translations':[{'id':'2','translation':'Power 75'}]}))
            result=merge_results(path,response,kind='excel')
            self.assertTrue(result['errors'])
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['images'],original['images'])

    def test_excel_retain_reason_must_be_text_and_pending_count_updates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.setup_job(Path(tmp),'excel')
            data=json.loads(path.read_text(encoding='utf-8')); data['pending_count']=3
            path.write_text(json.dumps(data),encoding='utf-8')
            index=export_batches(path,kind='excel'); response=path.parent/'response.json'
            response.write_text(json.dumps({'job_id':index['job_id'],'translations':[
                {'id':'1','translation':'标题','reason':None}, {'id':'2','translation':'Power 75kW'}]}),encoding='utf-8')
            report=merge_results(path,response,kind='excel')
            self.assertEqual([e['id'] for e in report['errors']],['1'])
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['pending_count'],2)


if __name__ == '__main__': unittest.main()
