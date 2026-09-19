#!/usr/bin/env python3
"""Stage four-arm development trials and optionally probe Docker isolation. No model calls."""
import argparse
import importlib.util
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('prepare', ROOT / 'paper/scripts/prepare-study-v1.py')
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
TASKS = ['H4-tsbuildinfo-trap', 'H6-remote-error-trap', 'H12-remote-result-boundary-trap', 'H25-session-seed-boundary-trap']
PROBE = r'''
import fs from 'node:fs';
import assert from 'node:assert/strict';
import http from 'node:http';
import net from 'node:net';
const mode=process.argv[2], task=process.argv[3];
assert.deepEqual(fs.readdirSync('/app').sort(), ['agent-output','fixture','instruction.md','materials']);
assert.ok(fs.readFileSync('/app/instruction.md','utf8').includes('BENCHMARK-MATERIALS-v1'));
assert.ok(fs.existsSync('/app/materials/ENTRY.md'));
assert.deepEqual(fs.readdirSync(process.env.HOME), []);
for(const path of ['/app/materials/ENTRY.md','/app/instruction.md','/app/fixture/README.md']) {
 let rejected=false;try{fs.appendFileSync(path,'X')}catch{rejected=true} assert.ok(rejected,path+' writable');
}
if(mode==='hands-on') {fs.appendFileSync('/app/fixture/src/fork-state.mjs','\n// isolated probe\n');}
else if(task.startsWith('H4-')) {fs.rmSync('/app/fixture/lib/index.js');}
else {let rejected=false;try{fs.appendFileSync('/app/fixture/src/'+(task.startsWith('H6-')?'remote-usage.ts':'index.ts'),'X')}catch{rejected=true}assert.ok(rejected);}
fs.writeFileSync('/app/agent-output/'+task+'/probe.txt','delivery-ok');
const server=http.createServer((q,r)=>r.end('local-ok'));
await new Promise(r=>server.listen(0,'127.0.0.1',r));
assert.equal(await (await fetch('http://127.0.0.1:'+server.address().port)).text(),'local-ok');server.close();
const escaped=await new Promise(resolve=>{const s=net.connect({host:'1.1.1.1',port:443});s.setTimeout(1500);s.on('connect',()=>{s.destroy();resolve(true)});s.on('error',()=>resolve(false));s.on('timeout',()=>{s.destroy();resolve(false)});});
assert.equal(escaped,false);
console.log(JSON.stringify({materialReadOnly:true,fixturePermissions:true,delivery:true,emptyHome:true,loopback:true,outboundBlocked:true}));
'''

def command(stage, row, image):
    # No caller HOME/config, repository, verifier, auth, socket, or other arms mounted.
    cmd=['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL',
         '--security-opt','no-new-privileges','--user','1000:1000','--pids-limit','128',
         '--memory','512m','--cpus','1','--tmpfs','/tmp:rw,nosuid,nodev,size=64m',
         '--tmpfs','/home/study:rw,nosuid,nodev,uid=1000,gid=1000,mode=700',
         '-e','HOME=/home/study','-e','STUDY_NATIVE_SKILLS=disabled']
    mounts=[(stage/'materials','/app/materials',True),(stage/'fixture','/app/fixture',True),
            (stage/'instruction.md','/app/instruction.md',True),(stage/'output','/app/agent-output',False),
            (stage/'probe.mjs','/probe.mjs',True)]
    if row['task'].startswith('H25-'):
        mounts.extend([(stage/'fixture/src','/app/fixture/src',False),(stage/'fixture/package.json','/app/fixture/package.json',False)])
    elif row['task'].startswith('H4-'):
        mounts.append((stage/'fixture/lib','/app/fixture/lib',False))
    for host,target,readonly in mounts:
        cmd+=['--mount',f'type=bind,src={host},dst={target}'+(',readonly' if readonly else '')]
    cmd+=['--entrypoint','node',image,'/probe.mjs', 'hands-on' if row['task'].startswith('H25-') else 'static',row['task']]
    return cmd


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True)
    parser.add_argument('--report',required=True)
    parser.add_argument('--docker-probe',action='store_true')
    parser.add_argument('--image',default='node:24-bookworm')
    args=parser.parse_args()
    destination=Path(args.out).resolve()
    if destination.exists() or destination==ROOT or ROOT in destination.parents:
        raise ValueError('use a fresh staging directory outside the repository')
    config=json.loads((p.STUDY/'config.json').read_text())
    manifest,packages,prompts,_=p.build_materials(config)
    destination.mkdir(parents=True)
    rows=[]
    for task in TASKS:
        t=next(t for t in manifest['tasks'] if t['task']==task)
        base='benchmark/tasks/'+task+'/environment/fixture'
        fixtures={path[len(base)+1:]:p.blob(config['sourceCommit'],path) for path in p.listing(config['sourceCommit'],base)}
        p.normalized_files(fixtures)
        for arm in 'ABCD':
            stage=destination/task/arm; stage.mkdir(parents=True)
            materials=packages[t['materialVariant']][arm]
            for directory,files in [('materials',materials),('fixture',fixtures)]:
                for name,data in files.items():
                    path=stage/directory/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            (stage/'instruction.md').write_bytes(prompts[task]);(stage/'probe.mjs').write_text(PROBE)
            (stage/'output'/task).mkdir(parents=True)
            # Writable permissions only within this disposable stage; bind mounts
            # enforce the effective ro/rw boundary during the container probe.
            for d in [stage/'output',stage/'output'/task,stage/'fixture/src']:
                d.chmod(0o777)
            if task.startswith('H4-'): (stage/'fixture/lib').chmod(0o777)
            if task.startswith('H25-'):
                (stage/'fixture/package.json').chmod(0o666)
                for f in (stage/'fixture/src').rglob('*'):
                    if f.is_file(): f.chmod(0o666)
            row={'task':task,'arm':arm,'developmentOnly':True,'materialSha256':p.package_hash(materials),
                 'promptSha256':p.sha(prompts[task]),'fixtureFiles':p.file_manifest(fixtures),
                 'materialBytes':sum(map(len,materials.values())),'materialTokens':None,
                 'inputTokens':None,'outputTokens':None,'actualCost':None,'solverExecuted':False}
            row['dockerCommand']=command(stage,row,args.image)
            # Check stage layout and provenance without interpreting this as an OS sandbox.
            assert set(x.name for x in stage.iterdir())=={'materials','fixture','instruction.md','output','probe.mjs'}
            assert p.package_hash({str(f.relative_to(stage/'materials')):f.read_bytes() for f in (stage/'materials').rglob('*') if f.is_file()})==row['materialSha256']
            assert not any(f.is_symlink() for f in stage.rglob('*'))
            row['stagingChecks']='passed';rows.append(row)
    report={'mode':'offline-stage-and-optional-container-probe','trials':rows,
            'selection':'H4/H6/H12 static and H25 hands-on are preselected QC development cases, not selected by new outcomes',
            'dockerIsolation':'not-tested','solverCalls':0,'judgeCalls':0,'observedModelSpend':0,
            'modelCostEstimate':None,'blockers':['model IDs/provider configuration and total spending cap unset',
            'live solver adapter with host-side transport and usage metering not implemented; probe image contains no solver',
            'H25 stage has source fixture only; install locked runtime in a builder before live use']}
    if args.docker_probe:
        info=subprocess.run(['docker','info','--format','{{.ServerVersion}}'],capture_output=True,text=True,timeout=15)
        if info.returncode:
            report['dockerIsolation']='blocked-daemon-unavailable'
            report['dockerError']=info.stderr.strip()
        else:
            image=subprocess.run(['docker','image','inspect','--format','{{.Id}}',args.image],capture_output=True,text=True,timeout=15)
            if image.returncode:
                report['dockerIsolation']='blocked-local-image-unavailable'
            else:
                report['imageId']=image.stdout.strip();report['dockerIsolation']='passed'
                for row in rows:
                    start=time.monotonic();done=subprocess.run(row['dockerCommand'],capture_output=True,text=True,timeout=30)
                    row['probeSeconds']=time.monotonic()-start;row['probeExitCode']=done.returncode
                    row['probeOutput']=done.stdout.strip();row['probeError']=done.stderr.strip()
                    if done.returncode: report['dockerIsolation']='failed';break
    output=Path(args.report);output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(p.encoded(report))
    print(f"Staged {len(rows)} development cells; docker={report['dockerIsolation']}; no model calls. Report: {output}")

if __name__=='__main__':main()
