"""Finish an already running initial collection, then run the council audit once."""
import argparse
import ctypes
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
STATUS = Path('data/full_site_workflow_status.json')


def status(phase, **extra):
    STATUS.write_text(json.dumps({'phase': phase, **extra},ensure_ascii=False,indent=2),encoding='utf-8')


def main(initial_pid):
    from ctypes import wintypes
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel.OpenProcess(0x00100000, False, initial_pid)
    if handle:
        status('waiting_for_initial_collection')
        try:
            while kernel.WaitForSingleObject(handle, 1000) == 0x102:
                time.sleep(4)
        finally:
            kernel.CloseHandle(handle)
    from crawler.site_sync import run_site_sync
    status('resuming_and_retrying_collection')
    report = run_site_sync(resume=True)
    if report.get('phase') == 'already_running' or report.get('counts',{}).get('pending'):
        status('collection_still_running')
        return
    status('evaluating_100_questions', coverage_counts=report.get('counts'))
    from scripts.audit_council_questions import run
    run(Path('data/faq_audit_inputs.json'),Path('data/council_faq_after_collection.json'))
    status('diagnostic_complete', coverage_counts=report.get('counts'),
           correctness_review='required; evidence counts are not accuracy')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--initial-pid',type=int,required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    try:
        main(args.initial_pid)
    except BaseException as exc:
        status('failed',error_type=type(exc).__name__)
        raise
