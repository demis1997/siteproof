import hashlib
import json
from pathlib import Path


def test_phase34_preserves_held_out_labels_and_website_groups():
    dataset=json.loads(Path('evals/phase34-dataset-v1.json').read_text())
    original=Path('evals/labels.json').read_bytes()
    assert hashlib.sha256(original).hexdigest()==dataset['held_out_labels_sha256']
    groups={}
    for fixture in dataset['fixtures']:
        groups.setdefault(fixture['website_group'],set()).add(fixture['split'])
    assert all(len(splits)==1 for splits in groups.values())
    held_out=[f for f in dataset['fixtures'] if f['split']=='test']
    assert held_out==json.loads(original)['fixtures']
