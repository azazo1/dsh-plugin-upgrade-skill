#!/usr/bin/env python3
"""Read-only historical-run compatibility audit; never changes historical scores."""
import argparse
import csv
import functools
import hashlib
import json
import re
import statistics
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'paper/study-v1/generated'
PREFIX = 'benchmark/results/validation-report-'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def packed(data):
    return (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode()


@functools.lru_cache(maxsize=None)
def git_blob(commit, path):
    return subprocess.check_output(['git', 'show', f'{commit}:{path}'], cwd=ROOT,
                                   stderr=subprocess.DEVNULL)


def extra_records():
    # Reported configurations, not reconstructed provider identities or manifests.
    data = {}
    def row(name, model, agent, scope, conditions, repeats, source, skill, grading, access,
            disposition, roots=(), notes=''):
        data[PREFIX + name + '.md'] = dict(
            model=model, agent=agent, scope=scope, conditions=conditions, repeats=repeats,
            benchmark_commit_reported=source, skill_commit_reported=skill, grading=grading,
            access_boundary=access, historicalDisposition=disposition,
            artifactRoots=['benchmark/results/' + p for p in roots], notes=notes)
    row('2026-09-07-generic-skill-s1-s10-kimi', 'Kimi Code; exact model ID unknown', 'Kimi Code CLI',
        'S1-S10', 'generic only', '1/task', 'unknown; pilot, not official snapshot',
        'generic-migration; exact hash not established', 'historical official judges in Docker',
        'instruction-fenced; macOS Docker, no physical no-network guarantee', 'local-answer-regrade-candidate',
        ['generic-arm-s1-s10'], 'Generic pilot is not a paired contrast with GLM results.')
    for suffix, scope in [('18', '18 tasks'), ('full56', '56 tasks; initial18 + remaining38')]:
        date = '2026-09-08' if suffix == '18' else '2026-09-09'
        row(f'{date}-codex-gpt-6-astra-xhigh-{suffix}', 'openai/gpt-6-astra xhigh',
            'Codex 0.153.4 / Harbor 0.22.0', scope, 'plugin-upgrade only', '1/task',
            '72267b6f83670d74965752aac525a989a5a0a1c0',
            '72267b6; H11=7d33bf4; H21=5f7234b where applicable', 'historical mixed graders',
            'native skills/plugins/memory/search disabled as reported; timeout multiplier 2',
            'recover-private-artifacts-first', notes='Raw archives retained by contributor. Initial18 is included in full56, not another 18 independent trials.')
    row('2026-09-10-codex-gpt-5.6-luna-h24-h25', 'gpt-5.6-luna xhigh', 'Codex 0.153.4 / Harbor 0.22.0',
        'H24/H25', 'no injected/native skill', '1/task', '5724542 + frozen uncommitted task fixes; JSON hashes',
        'none', 'deterministic behavior/static caps', 'public network; search disabled',
        'recover-private-artifacts-first', notes='H25 behavioral checks passed but helper-contract cap applied. Must resolve criterion before new main use.')
    row('2026-09-10-codex-gpt-5.6-luna-s1-s10-s12-s15-no-skill', 'gpt-5.6-luna xhigh',
        'Codex 0.153.4 / Harbor 0.22.0', 'S1/S10/S12/S15', 'no skill', '1/task',
        'b49ccee + uncommitted fixes; JSON hashes', 'none', 'regex/keyword grader with documented false negatives',
        'public network; search disabled; explicit no-skill prompt', 'local-answer-regrade-candidate',
        ['artifacts/2026-09-10-luna-s1-s10-s12-s15'], 'Regrade to audit old measurement, not to emulate new prompts.')
    row('2026-09-10-codex-gpt-5.6-luna-seven-semantic-no-skill', 'gpt-5.6-luna xhigh; judge Astra high',
        'Codex 0.153.4 / Harbor 0.22.0; host-side judge', 'S1-S4/S10/S12/S15', 'no skill', '1/task',
        'b49ccee + frozen workspace hashes', 'none', 'task 3.0.0 / report-judge-v1',
        'S4 no-network; other tasks public; no-skill overlay', 'local-answer-regrade-candidate',
        ['artifacts/2026-09-10-luna-seven-semantic-no-skill'], 'New solver answers, not regrades of the earlier four-task batch.')
    row('2026-09-10-default-semantic-verifiers', 'judge gpt-6-astra high', 'Codex judging transport / offline checks',
        '7 semantic tasks, selected calibration cases', 'calibration; not solver arms', '15 judge calls reported',
        'task/grader hashes in companion JSON', 'not applicable', 'task 3.0.0 / report-judge-v1',
        'no main solver experiment', 'calibration-only')
    row('2026-09-11-codex-gpt-5.6-luna-s5-s9-semantic-no-skill', 'gpt-5.6-luna xhigh; judge Astra high',
        'Codex 0.153.4 / Harbor 0.22.0; host-side judge', 'S5-S9', 'no skill', '1/task',
        'b49ccee + frozen workspace hashes', 'none', 'task 3.0.0 / report-judge-v1',
        'S5-S7 no-network; S8-S9 public; no-skill overlay', 'local-answer-regrade-candidate',
        ['artifacts/2026-09-11-luna-s5-s9-semantic-no-skill'])
    row('2026-09-11-codex-qwen3.8-27b-medium-paired', 'qwen3.8-27b medium; local BF16 H20',
        'Codex 0.153.4 / vLLM 0.28.0 / Harbor 0.22.0', '56 tasks / 336 attempts / 335 scores',
        'plugin-upgrade / no Harbor-injected skill', '3/arm/task; H8 baseline score missing',
        '74af446 + anti-cheat stripping/CRLF/shadow-image deltas',
        '74af446; H11/H21 task-specific pins', 'pre-fix H8/M5/S5/S6/S7 and historical mixed graders',
        'local serving; compaction and launcher changes disclosed; original task budgets',
        'recover-private-artifacts-first', notes='Raw sessions/candidate files not in submitted compact JSON; fixes during run need trial-specific protocol mapping.')
    for suffix in ['', '-round2', '-round3']:
        row('2026-09-11-glm-5.3-flash-s1-s22' + suffix, 'GLM-5.3-flash solver and judge',
            'DSH CLI subagents; exact executable version not established', 'S1-S22', 'skill / noskill',
            '1/arm/task in this round', 'f32175d (reported for all three rounds)',
            'plugin-upgrade entry + references; exact mounted manifest needs recovery',
            '10 keyword tasks + 12 semantic tasks; same-family judge',
            '3-4 subagents; complete network/native-catalog isolation not independently established',
            'local-answer-regrade-candidate', ['artifacts/2026-09-11-glm-5.3-flash-s1-s22' + suffix],
            'Round3 includes a three-round aggregate; do not count the aggregate as a fourth trial.')
    row('2026-09-11-s5-s9-default-semantic-verifiers', 'judge gpt-6-astra high', 'Codex judging transport',
        'S5-S9 / 20 calibration calls', 'oracle/paraphrase/keyword/contradiction controls', '1/case',
        '35275ac PR base; frozen grading bytes in JSON', 'not applicable', 'task 3.0.0 / report-judge-v1',
        'calibration, not a solver experiment', 'calibration-only')
    for suffix in ['no-skill', 'decision-judge']:
        row('2026-09-12-codex-luna-h4-h6-h12-' + suffix, 'gpt-5.6-luna xhigh solver / high judge',
            'Codex 0.153.4 / Harbor 0.22.0; host-side judge', 'H4/H6/H12',
            'no skill; same original answers across two reports',
            '1 solver/task; earlier H4/H6 judge retry only' if suffix == 'no-skill' else '0 new solver trials; 1 regrade/task',
            'local frozen files; provenance.json hashes', 'none',
            'task 3 / report-judge-v1' if suffix == 'no-skill' else 'task 4 / report-judge-v2',
            'no native skills; original fixture artifacts retained; judge isolated',
            'local-answer-regrade-candidate',
            ['artifacts/2026-09-12-luna-h4-h6-h12-semantic-no-skill',
             'artifacts/2026-09-12-luna-h4-h6-h12-decision-judge'],
            'H4/H6 initial judge errors are missing, not zero; decision-judge is a regrade, not another solver sample.')
    return data


def answer_files(root):
    paths = []
    for p in sorted(root.rglob('*')):
        if not p.is_file() or not p.name.endswith(('.md', '.txt')):
            continue
        rel = p.relative_to(root).as_posix()
        # Explicit report-root layouts, not arbitrary solutions/calibration prose.
        is_answer = (re.match(r'(skill|noskill)/[^/]+/report\.md$', rel) or
                     re.match(r'S\d+\.md$', rel) or
                     (re.match(r'[SH]\d+/', rel) and p.name not in ('README.md', 'test-stdout.txt')
                      and ('reports/' in rel or p.name in ('report.md', 'report.txt', 'report.md.txt',
                          'migration-report.md', 'migration-report.md.txt', 'assessment.md',
                          'touchpoint-report.md', 'REPORT.md', 'installation-type-baseline-plan.md.txt')))
                     or (root.name == 'generic-arm-s1-s10' and rel.endswith('/report.md')))
        if is_answer:
            paths.append(p)
    return paths


def packet_checks(roots, target):
    checks = []
    for root in roots:
        for p in sorted(root.rglob('packet.json')):
            d = json.loads(p.read_text())
            task = d.get('task')
            if not task or not isinstance(d.get('fixture'), dict):
                continue
            try:
                now = json.loads(git_blob(target, f'benchmark/tasks/{task}/tests/packet.json'))
            except (subprocess.CalledProcessError, json.JSONDecodeError):
                checks.append({'packet': str(p.relative_to(ROOT)), 'task': task,
                               'status': 'no-current-semantic-packet; manual mapping required'})
                continue
            def fixture_hashes(packet):
                result = {}
                for path, value in packet['fixture'].items():
                    if 'text' in value:
                        actual = sha(value['text'].encode())
                        if actual != value.get('sha256'):
                            raise ValueError(f'invalid embedded fixture hash: {p}:{path}')
                    result[path] = value.get('sha256')
                return result
            checks.append({'packet': str(p.relative_to(ROOT)), 'packetSha256': sha(p.read_bytes()),
                           'task': task, 'oldProtocol': d.get('protocol'), 'newProtocol': now.get('protocol'),
                           'fixtureIdentical': fixture_hashes(d) == fixture_hashes(now),
                           'originalInstructionIdentical': d.get('instruction') == now.get('instruction'),
                           'rubricIdentical': d.get('rubric') == now.get('rubric'),
                           'referenceContentIdentical': d.get('references') == now.get('references'),
                           'scope': 'input packet comparison only; exported candidate integrity gates still require verification'})
    return checks


def accounting():
    base = ROOT / 'benchmark/results'
    gp = base / 'artifacts/2026-09-11-glm-5.3-flash-s1-s22/usage-summary.json'
    data = json.loads(gp.read_text())
    totals = {a: {k: sum(v[k] for label, v in data.items() if label.startswith(a + ':'))
                  for k in ['in', 'out', 'cache', 'total', 'ms']} for a in ['skill', 'noskill']}
    qp = base / 'validation-report-2026-09-11-codex-qwen3.8-27b-medium-paired.json'
    q = json.loads(qp.read_text())
    deltas, timed = [], {a: 0 for a in ['with-skill', 'no-skill']}
    for row in q['per_task']:
        a = [v for v in row['with-skill']['rewards'] if v is not None]
        b = [v for v in row['no-skill']['rewards'] if v is not None]
        deltas.append(statistics.mean(a) - statistics.mean(b))
        for arm in timed:
            timed[arm] += sum(v == 1 and e == 'AgentTimeoutError' for v, e in
                              zip(row[arm]['rewards'], row[arm]['exceptions']))
    return {'status': 'descriptive-recalculation; raw files unchanged',
            'glm': {'source': str(gp.relative_to(ROOT)), 'sha256': sha(gp.read_bytes()),
                    'solverTotals': totals, 'skillToNoskillRatios': {
                        k: totals['skill'][k] / totals['noskill'][k] for k in totals['skill']},
                    'note': 'Separate judge calls excluded; total includes cache; ms sums sessions, not parallel wall time.'},
            'qwen': {'source': str(qp.relative_to(ROOT)), 'sha256': sha(qp.read_bytes()),
                     'equalTaskWeightAvailableRepeatDelta': statistics.mean(deltas),
                     'perfectWithTimeout': timed,
                     'note': 'H8 baseline repeat missing; this is not a complete paired estimate or confidence interval.'}}


def audit():
    config = json.loads((ROOT / 'paper/study-v1/config.json').read_text())
    legacy_path = ROOT / 'paper/audit/experiment-ledger.csv'
    legacy = {r['report']: r for r in csv.DictReader(legacy_path.read_text().splitlines())}
    extra = extra_records()
    records = []
    labels = {'local-answer-regrade-candidate': '有本地答案，可作历史重评候选',
              'recover-private-artifacts-first': '须先取回原始产物',
              'calibration-only': '仅作评分/开发校准',
              'historical-descriptive-only': '保留历史描述，不直接重评',
              'unresolved-report': '缺少配置核查，暂不复用'}
    for p in sorted((ROOT / 'benchmark/results').glob('validation-report-*.md')):
        key = str(p.relative_to(ROOT))
        if key in extra:
            record = dict(extra[key])
            origin = '2026-09-13 report-level audit; assertions are reported unless independently compared below'
        elif key in legacy:
            record = dict(legacy[key])
            origin = '2026-09-08 ledger retained; not a new raw-trace audit'
            cat = record.get('category', '')
            if 'paired-candidate' in cat or cat in ['incomplete', 'baseline-deviation', 'single-arm-calibration']:
                record['historicalDisposition'] = 'recover-private-artifacts-first'
            elif 'calibration' in cat or 'development' in cat or 'oracle' in cat:
                record['historicalDisposition'] = 'calibration-only'
            else:
                record['historicalDisposition'] = 'historical-descriptive-only'
        else:
            record = {'historicalDisposition': 'unresolved-report', 'notes': 'No curated audit entry; do not infer compatibility.'}
            origin = 'unreviewed report'
        prior_sha = record.pop('report_sha256', None)
        roots = [ROOT / r for r in record.get('artifactRoots', [])]
        answers = sorted({p for root in roots for p in answer_files(root)})
        linked = []
        for dest in re.findall(r'\]\(([^)]+)\)', p.read_text()):
            if '://' in dest or dest.startswith('#'):
                continue
            path = (p.parent / dest.split('#')[0]).resolve()
            if ROOT in path.parents and path.is_file():
                linked.append({'path': str(path.relative_to(ROOT)), 'sha256': sha(path.read_bytes())})
        disposition = record['historicalDisposition']
        record.update({'report': key, 'reportSha256': sha(p.read_bytes()), 'auditBasis': origin,
                       'legacyReportSha256Matches': prior_sha == sha(p.read_bytes()) if prior_sha else None,
                       'localLinkedEvidence': linked,
                       'localCandidateReports': [{'path': str(a.relative_to(ROOT)), 'sha256': sha(a.read_bytes())} for a in answers],
                       'packetComparisons': packet_checks(roots, config['sourceCommit']),
                       'newStudyDecision': 'rerun-required-for-current-candidate-protocol',
                       'newStudyReasons': ['new common material-access prompt is absent from historical run',
                                           'A/B/C/D material hashes, delivery and shared tool boundary not established equal',
                                           'new model/budget/repetition protocol remains unfrozen'],
                       'regradeScope': 'historical measurement audit only; never simulate a changed solver input',
                       'historicalAction': labels[disposition]})
        if disposition == 'local-answer-regrade-candidate' and not answers:
            record['historicalDisposition'] = 'recover-private-artifacts-first'
            record['historicalAction'] = labels['recover-private-artifacts-first']
            record['notes'] = record.get('notes', '') + ' No recognized candidate report found locally.'
        records.append(record)
    return {'schemaVersion': 1, 'auditDate': '2026-09-13', 'targetConfigSha256': sha(packed(config)),
            'targetSourceCommit': config['sourceCommit'], 'targetState': 'candidate-not-frozen',
            'formalMainReuseApproved': 0, 'legacyLedgerSha256': sha(legacy_path.read_bytes()),
            'records': records, 'accountingChecks': accounting(),
            'rule': 'A regrade changes measurement, not solver inputs. Local answer availability is not certification that all integrity gates can be replayed.'}


def markdown(data):
    lines = ['# 旧实验兼容性清单', '', '本清单针对当前四条件候选协议，不覆盖未公开轨迹的实地复现。原报告和原分数不改写。', '',
             f"覆盖 **{len(data['records'])} 份报告**；当前没有旧 trial 获准直接填入新主表。", '',
             '## 结论与执行顺序', '',
             '1. 先重评本地有答案的静态历史批次，检查换评分器后结论是否改变；这些是测量审计，不是新的四条件主实验。',
             '2. Astra、Qwen、早期 Flash/Terra 等先向贡献者取回候选补丁/完整 fixture、原提示、挂载资料与运行配置；只有分数无法重新评分。',
             '3. 新 D−C 主实验按新提示和材料重跑各条件。不能把重评后的旧 A/D 拼上新 C 就当受控比较。',
             '4. 仅 rubric 改变且原始输入/候选产物完整时可重评；fixture、提示、资料、工具或预算改变须重跑。', '',
             '## 逐报告决策', '', '| 报告 | 模型 / 范围 | 条件 / 重复 | 历史用途 | 本地答案数 |', '|---|---|---|---|---:|']
    for r in data['records']:
        name = Path(r['report']).stem.replace('validation-report-', '')
        rel = '../../../' + r['report']
        cell = lambda x: str(x).replace('|', '/').replace('\n', ' ')
        lines.append(f"| [{name}]({rel}) | {cell(r.get('model','unknown'))}; {cell(r.get('scope','unknown'))} | {cell(r.get('conditions','unknown'))}; {cell(r.get('repeats','unknown'))} | {r['historicalAction']} | {len(r['localCandidateReports'])} |")
    lines += ['', '本地答案数按报告关联计算，存在重复关联，不能求和当作独立 trial 总数。逐文件 SHA、packet 逐项比较、模型/scaffold/skill/评分版本和资料边界见 `compatibility.json`。', '',
              '## 重评前还要检查', '',
              '- GLM 三轮：本地保存两臂答案；统一裁判后每轮两臂全部重评，先确认 sealed fixture 与提示版本一致。历史关键词/语义分不能混作统一新版分数。',
              '- Luna 四题／七题／五题：本地保存静态答案；七题是新作答，不是四题旧答案重评。仅无 skill，重评也不能给出配对 skill 效果。',
              '- H4/H6/H12：decision-judge 已对原答案重评；两个报告共享三份 solver 答案，不是六份。H4删除构建产物的例外需保留候选完整性证据。',
              '- Generic Kimi pilot：若本地答案齐全可审计旧评分，但模型/scaffold不同，不能拿来与 GLM/Astra 做条件差分。',
              '- H24/H25：紧凑 JSON 不等于完整可执行补丁；H25 helper 封顶争议需先判定契约，再决定历史重评标准。',
              '- Astra initial18 已计入 full56；GLM round3 中的中位数汇总不是第四轮；元数据 activation pilot 的原始临时轨迹据报告已删除。', '',
              '## 已发现的统计口径问题', '']
    a = data['accountingChecks']
    ratios = a['glm']['skillToNoskillRatios']
    lines += [f"- GLM 首轮：按各 22 条 solver 用量汇总，total token 比例为 **{ratios['total']:.4f}**，累计会话耗时比例为 **{ratios['ms']:.4f}**。报告中约 2.2 倍／翻倍的说法需修正；累计会话时间不等于并行墙钟。",
              f"- Qwen：按每题现有有效重复均值、56 题等权，差为 **{100*a['qwen']['equalTaskWeightAvailableRepeatDelta']:.4f} pp**；H8仍缺一分数，不是完整配对估计。skill/no-skill 分别有 **{a['qwen']['perfectWithTimeout']['with-skill']}/{a['qwen']['perfectWithTimeout']['no-skill']}** 个 timeout 且满分的 trial，超时不等于功能失败。",
              '- 上述是原 JSON 的可复算补充，不覆盖或修饰原始记录；正式区间、分组与缺失敏感性分析另做。', '']
    return '\n'.join(lines).encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    data = audit()
    files = {OUT / 'compatibility.json': packed(data), OUT / 'COMPATIBILITY.zh.md': markdown(data)}
    for p, content in files.items():
        if args.check:
            if not p.exists() or p.read_bytes() != content:
                raise SystemExit(f'compatibility audit drift: {p}; regenerate and review')
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content)
    unique = {a['sha256'] for r in data['records'] for a in r['localCandidateReports']}
    print(f"{len(data['records'])} reports; {len(unique)} distinct candidate answer hashes located; no formal reuse approved")


if __name__ == '__main__':
    main()
