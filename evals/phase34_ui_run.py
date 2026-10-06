"""Execute trusted UI checks inside isolated Compose test tooling."""
import json
import subprocess
from pathlib import Path

from stack_run import COMPOSE


def main():
    root=Path('evals/reports/phase34')
    identifier=json.loads((root/'pipeline.json').read_text())['job_id']
    name='siteproof-phase34-ui'
    subprocess.run(['docker','rm','-f',name],capture_output=True,check=False)
    try:
        subprocess.run(COMPOSE+['--profile','ui-test','run','--name',name,'--no-deps','ui-test','python','evals/phase34_ui.py',identifier],check=True)
        for filename in ('phase34-ui.json','phase34-comparison.png','phase34-verification.png'):
            subprocess.run(['docker','cp',name+':/tmp/'+filename,str(root/filename)],check=True)
    finally:
        subprocess.run(['docker','rm','-f',name],capture_output=True,check=False)


if __name__=='__main__':
    main()
