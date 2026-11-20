#!/usr/bin/env python3
"""
Thử nghiệm Laya (pip: laya) cho 2 quyết định model 1.7B đang làm sai — đo trên dữ liệu của repo:

  ref       : trường này trỏ tới chức năng nào (hoặc không)?  đáp án = quan hệ trong spec
  coverage  : ý này trong mô tả ứng với trường nào (hoặc không)? đáp án = eval/coverage_cases.yaml,
              kèm biến thể bỏ trường đúng khỏi danh sách ⇒ phải trả "none" (phát hiện trường bị sót)

    python scripts/laya_eval.py --engine multilingual   # encoder mmBERT (~322M), nhanh trên CPU
    python scripts/laya_eval.py --engine vega           # engine 0.5.0 (bộ đọc 0.8B), có abstain/route
Kết quả: bảng Markdown (in ra + out/laya/report-<engine>.md) và JSON chi tiết.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from codegen import model  # noqa: E402

NONE = 'none'


def load_agent(engine):
    import laya
    if engine == 'multilingual':
        return laya.load("convaiinnovations/laya", subfolder="multilingual")
    if engine == 'english':
        return laya.load("convaiinnovations/laya")
    return laya.Agent(vegaml=True)


def ref_cases(ir):
    fns = {f['entity']: f for f in ir['functions'] if f['entity']}
    out = []
    for e in ir['entities']:
        fn = fns.get(e['id'])
        if not fn:
            continue
        options = {f['id']: f"{f['name']} (bảng {ir_ent(ir, f['entity'])['label']}, khoá {', '.join(ir_ent(ir, f['entity'])['pk'])})"
                   for f in fns.values() if f['id'] != fn['id']}
        options[NONE] = "không trỏ tới bảng nào khác, là dữ liệu riêng của bảng này"
        truth = {r['cols'][0]: r['parent_function'] for r in fn['refs'] if len(r['cols']) == 1 and r['parent_function']}
        for f in e['base_api_fields']:
            if f['from_profile'] or f['name'] in e['pk'] and f['name'] not in truth:
                continue
            state = f"Bảng '{e['label']}' có trường '{f['label']}' (tên cột {f['name']}, kiểu {f['type']})."
            out.append({'kind': 'ref', 'state': state, 'options': options, 'truth': truth.get(f['name'], NONE),
                        'id': f"{fn['id']}.{f['name']}"})
    return out


def ir_ent(ir, eid):
    return next(e for e in ir['entities'] if e['id'] == eid)


def coverage_cases(ir):
    data = yaml.safe_load((ROOT / 'eval/coverage_cases.yaml').read_text(encoding='utf-8'))
    fns = {f['id']: f for f in ir['functions']}
    out = []
    for c in data['cases']:
        if c.get('fields'):
            fields = {x['name']: x['label'] for x in c['fields']}
        else:
            e = ir_ent(ir, fns[c['function']]['entity'])
            fields = {f['name']: f['label'] for f in e['base_api_fields'] if not f['from_profile']}
        for cl in c['clauses']:
            opts = {k: v for k, v in fields.items()}
            opts[NONE] = "không ứng với trường nào (là luật nghiệp vụ, ràng buộc, hoặc trường chưa có)"
            out.append({'kind': 'coverage', 'state': f"Mô tả chức năng có ý: \"{cl['text']}\"", 'options': opts,
                        'truth': cl['field'], 'id': f"{c['function']}:{cl['text'][:30]}"})
            if cl['field'] != NONE:                       # biến thể: trường đúng bị sót khỏi spec
                miss = {k: v for k, v in opts.items() if k != cl['field']}
                out.append({'kind': 'missing', 'state': out[-1]['state'], 'options': miss, 'truth': NONE,
                            'id': f"{c['function']}:-{cl['field']}"})
    return out


QUESTION = {
    'ref': "Trường này lưu mã của bản ghi thuộc chức năng nào?",
    'coverage': "Ý này ứng với trường nào của bảng?",
    'missing': "Ý này ứng với trường nào của bảng?",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--engine', choices=['multilingual', 'english', 'vega'], default='multilingual')
    a = ap.parse_args()
    ir, rep = model.build_ir(ROOT / 'spec')
    if rep.errors:
        sys.exit('\n'.join(rep.errors))
    cases = ref_cases(ir) + coverage_cases(ir)
    t0 = time.time()
    agent = load_agent(a.engine)
    load_s = time.time() - t0
    results, t1 = [], time.time()
    for c in cases:
        q = {'q': {'type': 'choice', 'instructions': QUESTION[c['kind']], 'criteria': c['options']}}
        ans = agent.predict(c['state'], q)['answers']['q']
        probs = ans.get('probabilities') or {}
        results.append({**{k: c[k] for k in ('kind', 'id', 'truth')}, 'choice': ans.get('choice'),
                        'p': round(float(probs.get(ans.get('choice'), 0) or 0), 3),
                        'route': ans.get('route'), 'abstain': ans.get('abstain'),
                        'set': ans.get('prediction_set')})
    run_s = time.time() - t1

    L = [f"## Laya `{a.engine}` — {len(cases)} câu hỏi · nạp {load_s:.0f}s · chạy {run_s:.0f}s "
         f"({1000 * run_s / max(1, len(cases)):.0f} ms/câu)", '',
         '| Loại | Số câu | Đúng | Đúng khi route=auto | Tỉ lệ đẩy sang review |', '|---|---|---|---|---|']
    for kind, label in [('ref', 'tham chiếu'), ('coverage', 'ý → trường'), ('missing', 'phát hiện trường bị sót')]:
        rs = [r for r in results if r['kind'] == kind]
        if not rs:
            continue
        ok = sum(r['choice'] == r['truth'] for r in rs)
        auto = [r for r in rs if r['route'] in (None, 'auto')]
        ok_auto = sum(r['choice'] == r['truth'] for r in auto)
        review = 1 - len(auto) / len(rs)
        L.append(f"| {label} | {len(rs)} | {ok}/{len(rs)} ({100 * ok / len(rs):.0f}%) | "
                 f"{ok_auto}/{len(auto) or 1} | {100 * review:.0f}% |")
    L += ['', '<details><summary>Câu sai</summary>', '', '| Loại | Câu | Đáp án | Laya | p | route |', '|---|---|---|---|---|---|']
    L += [f"| {r['kind']} | `{r['id']}` | {r['truth']} | {r['choice']} | {r['p']} | {r['route']} |"
          for r in results if r['choice'] != r['truth']]
    L += ['', '</details>']
    report = '\n'.join(L)
    print(report)
    out = ROOT / 'out' / 'laya'
    out.mkdir(parents=True, exist_ok=True)
    (out / f"report-{a.engine}.md").write_text(report, encoding='utf-8')
    (out / f"results-{a.engine}.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
