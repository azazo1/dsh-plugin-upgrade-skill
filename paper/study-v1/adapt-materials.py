"""Versioned document-only edits. No task answers, solvers or grader input consumed."""
import re

def adapt_reference(path, raw):
    if not path.endswith('.md'):
        return raw
    text = raw.decode()
    if path == 'references/precision-checklist.md':
        start = text.index('## Landing discipline')
        end = text.index('## Peer version floors')
        text = text[:start] + 'Delivery scope and output location are defined by the common task brief.\nChecks below describe engineering contracts; record checks that cannot run.\n\n' + text[end:]
        text = text.replace('Run `node scripts/inject-lint.mjs <fixture-dir>` (shipped with this skill) for\na residue and peer check:', 'With ordinary installed search tools, inspect the following residue and peer conditions:')
    if path == 'references/pre-flight.md':
        text = re.sub(r'Both checks plus the probe are packaged as\n.*?exit 1 = ghost, so shell gates can consume the verdict directly\)\.',
                      'Use the process-time comparison and behavioral probe described above with ordinary installed tools; no packaged helper is supplied.', text, flags=re.S)
    # Links to absent helper/example/source-report directories become provenance
    # labels, never an instruction to fetch a missing executable. Applied after
    # construction to resolve links against the real package file set.
    return text.encode()

def neutralize_missing_links(files, missing):
    result = dict(files)
    for item in missing:
        path, target = item['file'], item['target']
        text = result[path].decode()
        text = re.sub(r'\[([^\]]+)\]\(' + re.escape(target) + r'\)',
                      lambda m: m[1] + ' (source attachment not supplied)', text)
        result[path] = text.encode()
    return result
