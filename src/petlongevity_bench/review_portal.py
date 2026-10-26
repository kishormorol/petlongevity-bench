"""Build a static, local-first full-paper clinician annotation portal."""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .fulltext import validate_fulltext_receipts
from .io import load_jsonl


def build_fulltext_review_portal(
    registry_path: str | Path,
    receipts_path: str | Path,
    base_dir: str | Path,
    output_path: str | Path,
) -> dict[str, int]:
    """Write a standalone reviewer page from validated full-paper receipts.

    The page stores draft entries only in the reviewer's browser and downloads JSONL for the
    coordinator. It never transmits annotations or promotes them to benchmark gold.
    """
    errors = validate_fulltext_receipts(receipts_path, registry_path, base_dir)
    if errors:
        raise ValueError("cannot build portal from invalid full-text receipts")
    papers = {row["paper_id"]: row for row in load_jsonl(registry_path)}
    root = Path(base_dir)
    sources: list[dict[str, Any]] = []
    for receipt in load_jsonl(receipts_path):
        paper = papers[receipt["paper_id"]]
        source_path = root / receipt["source_text_path"]
        sources.append({
            "paper_id": paper["paper_id"],
            "paper_title": paper["title"],
            "species": paper["species"],
            "publication_date": paper.get("publication_date"),
            "source_text_path": receipt["source_text_path"],
            "source_text_sha256": receipt["source_text_sha256"],
            "license_or_permission": receipt["license_or_permission"],
            "text": source_path.read_text(encoding="utf-8"),
        })
    payload = json.dumps(sources, ensure_ascii=False).replace("</", "<\\/")
    page = _portal_html(payload, len(sources))
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(page, encoding="utf-8")
    return {"paper_count": len(sources)}


def _portal_html(payload: str, paper_count: int) -> str:
    """Return the static portal shell; all draft data remains client-side."""
    template = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PetLongevity-Bench — Full-paper annotation</title>
<style>
:root{{--ink:#13313d;--navy:#092c48;--teal:#087d75;--mint:#e5f6ef;--cream:#fafbf8;--line:#d3e3df;--muted:#5d7075;--gold:#bd8529;--red:#b4455c}}*{{box-sizing:border-box}}body{{margin:0;background:var(--cream);color:var(--ink);font:15px/1.55 Arial,sans-serif}}.shell{{max-width:1440px;margin:auto;padding:0 26px}}header{{background:linear-gradient(115deg,var(--navy),#0a6666);color:#fff;padding:28px 0}}.eyebrow{{color:#a6e8d7;text-transform:uppercase;letter-spacing:.14em;font-size:.68rem;font-weight:bold}}h1,h2,h3{{font-family:Georgia,serif}}h1{{font-size:clamp(2rem,4vw,3.5rem);letter-spacing:-.045em;line-height:.98;margin:8px 0 12px}}header p{{max-width:750px;color:#d7efed;margin:0}}.privacy{{display:inline-block;margin-top:16px;padding:5px 9px;border:1px solid #94d6ca;border-radius:99px;font-size:.72rem;font-weight:bold}}main{{padding:25px 0 60px}}.notice{{background:#fff8e8;border-left:4px solid var(--gold);padding:13px 15px;color:#5e470f;margin-bottom:18px}}.workspace{{display:grid;grid-template-columns:285px minmax(360px,1fr) 390px;gap:16px;align-items:start}}.panel{{background:#fff;border:1px solid var(--line);border-radius:12px;overflow:hidden;box-shadow:0 7px 18px #0b3d4a0b}}.panel-head{{padding:15px 17px;border-bottom:1px solid var(--line)}}.panel-head h2{{font-size:1.24rem;color:var(--navy);margin:0 0 3px}}.small{{font-size:.78rem;color:var(--muted)}}.papers{{max-height:74vh;overflow:auto;padding:7px}}.paper{{width:100%;text-align:left;border:0;border-left:3px solid transparent;background:transparent;padding:12px 11px;cursor:pointer;color:var(--ink)}}.paper:hover,.paper.active{{background:#eff9f5;border-left-color:var(--teal)}}.paper b{{display:block;font-size:.86rem;line-height:1.28}}.paper span{{display:block;margin-top:4px;color:var(--muted);font-size:.72rem}}.reader{{padding:15px}}.paper-meta{{display:flex;gap:7px;flex-wrap:wrap;margin:7px 0 12px}}.chip{{border-radius:99px;background:var(--mint);color:#08685f;padding:3px 7px;font-size:.68rem;font-weight:bold}}textarea,input,select{{width:100%;border:1px solid #b9ceca;border-radius:7px;background:#fff;color:var(--ink);font:inherit;padding:8px}}textarea:focus,input:focus,select:focus{{outline:2px solid #6bc6b3;outline-offset:1px}}#source{{height:58vh;resize:vertical;white-space:pre-wrap;line-height:1.55;font:13px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;background:#fbfefd}}.selection{{display:flex;justify-content:space-between;gap:9px;align-items:center;margin-top:10px}}button{{border:0;border-radius:7px;background:var(--teal);color:white;font:700 .8rem Arial,sans-serif;padding:9px 11px;cursor:pointer}}button:hover{{background:#05685f}}button.secondary{{background:#e9f3f0;color:#174f52}}button.danger{{background:#f9e4e8;color:#8d2941}}.form{{padding:16px}}label{{display:block;margin:10px 0 4px;font-size:.72rem;font-weight:bold;color:#395b60;text-transform:uppercase;letter-spacing:.055em}}.two{{display:grid;grid-template-columns:1fr 1fr;gap:9px}}.quote{{height:82px;background:#f6fbf9}}.form-actions{{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}}.drafts{{border-top:1px solid var(--line);padding:14px 16px}}.draft{{border-top:1px solid #e4eeeb;padding:10px 0;font-size:.78rem}}.draft:first-child{{border-top:0}}.draft b{{display:block;line-height:1.3}}.draft small{{color:var(--muted)}}.hidden{{display:none}}footer{{padding:22px 0;border-top:1px solid var(--line);color:var(--muted);font-size:.78rem}}@media(max-width:1100px){{.workspace{{grid-template-columns:250px 1fr}}.annotation{{grid-column:1/-1}}}}@media(max-width:700px){{.shell{{padding:0 15px}}.workspace{{grid-template-columns:1fr}}.papers{{max-height:260px}}.annotation{{grid-column:auto}}#source{{height:44vh}}.two{{grid-template-columns:1fr}}}}
</style></head><body><header><div class="shell"><div class="eyebrow">PetLongevity-Bench · draft clinician review</div><h1>Annotate the evidence. Preserve the scope.</h1><p>Select exact text from a rights-cleared full paper. The portal captures the evidence quote and its character offsets automatically, then saves your draft locally until you download it for the coordinator.</p><span class="privacy">Local-first: nothing is uploaded from this page</span></div></header><main class="shell"><div class="notice"><b>Research annotation only.</b> Do not provide treatment recommendations, dosing, or patient-specific advice. Every entry is a draft and requires independent second review and adjudication before it can become benchmark gold.</div><div class="workspace"><aside class="panel"><div class="panel-head"><h2>Source papers</h2><span class="small">__PAPER_COUNT__ validated, rights-cleared texts</span></div><div id="papers" class="papers"></div></aside><section class="panel"><div class="panel-head"><div class="eyebrow" style="color:var(--teal)">Read and select</div><h2 id="paper-title">Loading source…</h2><div id="paper-meta" class="paper-meta"></div></div><div class="reader"><textarea id="source" readonly aria-label="Full paper source text"></textarea><div class="selection"><span id="selection-status" class="small">Select exact evidence text, then capture it.</span><button id="capture" type="button">Use selected evidence</button></div></div></section><aside class="panel annotation"><div class="panel-head"><h2>Draft annotation</h2><span class="small">One claim per saved entry</span></div><form id="form" class="form"><label for="reviewer">Reviewer ID</label><input id="reviewer" required placeholder="e.g., clinician_01"><div class="two"><div><label for="section">Paper section</label><input id="section" placeholder="e.g., Results"></div><div><label for="label">Judgment</label><select id="label" required><option value="">Select…</option><option value="supported">Supported</option><option value="contradicted">Contradicted</option><option value="insufficient">Insufficient</option></select></div></div><label for="claim">Claim as written</label><textarea id="claim" rows="3" required placeholder="Write one atomic claim to assess."></textarea><label for="quote">Exact evidence quote</label><textarea id="quote" class="quote" readonly required placeholder="Select text in the source pane."></textarea><div class="two"><div><label for="start">Start offset</label><input id="start" readonly></div><div><label for="end">End offset</label><input id="end" readonly></div></div><label for="design">Actual study design</label><input id="design" required placeholder="e.g., controlled trial"><label for="outcome">Outcome assessed</label><input id="outcome" required placeholder="e.g., cognitive score"><label for="causal">Causal interpretation</label><input id="causal" required placeholder="e.g., association only / causal support"><label for="notes">Limitations and reviewer notes</label><textarea id="notes" rows="3" placeholder="Scope limits, uncertainty, subgroup restrictions, or reason for insufficient."></textarea><div class="form-actions"><button type="submit">Save draft entry</button><button id="download" class="secondary" type="button">Download JSONL</button></div></form><div class="drafts"><b id="draft-count">0 draft entries</b><div id="draft-list"></div></div></aside></div></main><footer><div class="shell">Source texts are displayed only from validated receipts with recorded lawful access and license/permission. Downloaded annotations must be returned to the study coordinator for validation; they are not automatically submitted to GitHub or treated as gold data.</div></footer><script id="source-data" type="application/json">__PAYLOAD__</script><script>
const papers=JSON.parse(document.querySelector('#source-data').textContent);let current=0;let drafts=[];const $=s=>document.querySelector(s);const key=()=>`petbench-fulltext-drafts:${$('#reviewer').value.trim()||'unassigned'}`;const esc=s=>{{const e=document.createElement('span');e.textContent=s??'';return e.innerHTML}};
function loadDrafts(){{try{{drafts=JSON.parse(localStorage.getItem(key())||'[]')}}catch{{drafts=[]}}renderDrafts()}}function saveDrafts(){{localStorage.setItem(key(),JSON.stringify(drafts));renderDrafts()}}function renderPapers(){{$('#papers').innerHTML=papers.map((p,i)=>`<button type="button" class="paper ${{i===current?'active':''}}" data-i="${{i}}"><b>${{esc(p.paper_title)}}</b><span>${{esc(p.species.join(' · '))}} · ${{esc(p.publication_date||'date unavailable')}}</span></button>`).join('');document.querySelectorAll('.paper').forEach(b=>b.onclick=()=>{{current=Number(b.dataset.i);render()}})}}function render(){{const p=papers[current];$('#paper-title').textContent=p.paper_title;$('#paper-meta').innerHTML=`<span class="chip">${{esc(p.paper_id)}}</span><span class="chip">${{esc(p.species.join(' / '))}}</span><span class="chip">${{esc(p.license_or_permission)}}</span>`;$('#source').value=p.text;$('#quote').value='';$('#start').value='';$('#end').value='';$('#selection-status').textContent='Select exact evidence text, then capture it.';renderPapers()}}$('#capture').onclick=()=>{{const s=$('#source'),a=s.selectionStart,b=s.selectionEnd;if(a===b){{$('#selection-status').textContent='Please select a non-empty exact span first.';return}}$('#quote').value=s.value.slice(a,b);$('#start').value=a;$('#end').value=b;$('#selection-status').textContent=`Captured ${{b-a}} characters from the current paper.`}};$('#reviewer').addEventListener('change',loadDrafts);$('#form').onsubmit=e=>{{e.preventDefault();const p=papers[current];if(!$('#quote').value){{$('#selection-status').textContent='Capture an exact evidence span before saving.';return}}drafts.push({{paper_id:p.paper_id,paper_title:p.paper_title,species:p.species.join(';'),source_text_path:p.source_text_path,source_text_sha256:p.source_text_sha256,reviewer_id:$('#reviewer').value.trim(),source_section:$('#section').value.trim(),start_char:Number($('#start').value),end_char:Number($('#end').value),exact_evidence_quote:$('#quote').value,claim_text:$('#claim').value.trim(),draft_label:$('#label').value,study_design:$('#design').value.trim(),outcome:$('#outcome').value.trim(),causal_interpretation:$('#causal').value.trim(),reviewer_notes:$('#notes').value.trim()}});saveDrafts();['section','claim','label','quote','start','end','design','outcome','causal','notes'].forEach(id=>$('#'+id).value='');$('#selection-status').textContent='Draft saved locally. You can annotate another claim.'}};function renderDrafts(){{$('#draft-count').textContent=`${{drafts.length}} draft entr${{drafts.length===1?'y':'ies'}}`;$('#draft-list').innerHTML=drafts.slice().reverse().map((d,i)=>`<div class="draft"><b>${{esc(d.claim_text)}}</b><small>${{esc(d.paper_id)}} · ${{esc(d.draft_label)}} · offsets ${{d.start_char}}–${{d.end_char}}</small><button class="danger" type="button" data-i="${{drafts.length-1-i}}">Remove</button></div>`).join('');document.querySelectorAll('.danger').forEach(b=>b.onclick=()=>{{drafts.splice(Number(b.dataset.i),1);saveDrafts()}})}}$('#download').onclick=()=>{{if(!drafts.length){{alert('Save at least one draft entry before downloading.');return}}const lines=drafts.map(d=>JSON.stringify(d)).join('\n')+'\n',blob=new Blob([lines],{{type:'application/x-ndjson'}}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`petbench-fulltext-${{($('#reviewer').value.trim()||'reviewer')}}.jsonl`;a.click();URL.revokeObjectURL(a.href)}};loadDrafts();render();
</script></body></html>'''
    # Keep JavaScript newline escapes literal in the generated page.  Without this,
    # Python turns them into physical line breaks inside a single-quoted JS string.
    template = template.replace(
        "drafts.map(d=>JSON.stringify(d)).join('\n')+'\n',blob",
        r"drafts.map(d=>JSON.stringify(d)).join('\n')+'\n',blob",
    )
    template = template.replace(
        "</style>",
        """.how{display:grid;grid-template-columns:repeat(4,1fr);gap:9px;margin:0 0 12px}.step{background:#fff;border:1px solid var(--line);border-radius:10px;padding:12px}.step b{display:block;color:var(--teal);font-size:.7rem;letter-spacing:.08em;text-transform:uppercase}.step span{display:block;margin-top:4px;font-size:.8rem;color:#405a60}.plain-guide{background:#e8f6f2;border:1px solid #b9ded3;border-radius:11px;padding:16px 18px;margin:0 0 18px}.plain-guide h2{color:var(--navy);font-size:1.16rem;margin:0 0 4px}.plain-guide p{margin:4px 0}.plain-guide ol{margin:8px 0 0;padding-left:20px}.example{margin-top:10px;padding:10px 12px;background:#fff;border-radius:7px;font-size:.82rem}.progress{margin:10px 0 3px;padding:9px 10px;border-radius:7px;background:#edf8f4;color:#20685f;font-size:.76rem;font-weight:bold}.auto{margin:10px 0;padding:8px 10px;background:#eef8f4;border-radius:7px;color:#20685f;font-size:.75rem}.guide{margin:12px 0 2px;padding:11px;background:#edf8f4;border-radius:8px;font-size:.76rem;color:#37575b}.guide b{color:var(--teal)}.help{display:block;color:var(--muted);font-size:.72rem;text-transform:none;letter-spacing:0;font-weight:normal;margin-top:2px}@media(max-width:700px){.how{grid-template-columns:1fr 1fr}}""" + "</style>",
    ).replace(
        '<div class="workspace">',
        '''<section class="how" aria-label="How to annotate"><div class="step"><b>1. Pick a finding</b><span>Choose one factual result—not advice—from a paper.</span></div><div class="step"><b>2. Find its proof</b><span>Highlight one sentence or table row that states the result.</span></div><div class="step"><b>3. Record your judgment</b><span>Say whether that exact text supports the claim.</span></div><div class="step"><b>4. Save and send</b><span>Save each finding, then download one file when finished.</span></div></section><p class="guide"><b>First time here?</b> <a href="annotation_walkthrough.mp4" target="_blank">Watch the 48-second practice walkthrough video.</a> It demonstrates one draft entry only; it is not clinical advice or benchmark gold data.</p><section class="plain-guide"><h2>Your only job: record what the paper says</h2><p>An <b>annotation</b> is one small, checkable record: <b>a claim</b> + <b>the exact words or table row proving it</b> + <b>your cautious interpretation</b>.</p><ol><li>Do <b>not</b> diagnose, recommend treatment, or decide what a patient should do.</li><li>Do <b>not</b> invent a claim. Keep it limited to this paper, this species, and this measured outcome.</li><li>If the paper cannot answer the claim, choose <b>Insufficient</b>. That is a useful correct answer.</li></ol><div class="example"><b>Example only:</b> Claim: “This study found 56 dogs with at least one skin mass.” Highlight the sentence reporting that number. Choose <b>Supported</b>. Study type: <b>prospective screening study</b>. Outcome: <b>number of dogs with skin masses</b>. Causal conclusion: <b>association only / no intervention tested</b>.</div></section><div class="workspace">''',
    ).replace(
        '<h2>Draft annotation</h2><span class="small">One claim per saved entry</span>',
        '<h2>Complete one annotation</h2><span class="small">One claim per saved entry</span><div id="progress" class="progress">Before saving: complete the short questions below.</div>',
    ).replace(
        'Paper section</label><input id="section" placeholder="e.g., Results">',
        'Where in the paper?</label><span class="help">Choose the section containing the text you highlighted.</span><select id="section" required><option value="">Choose a section…</option><option>Abstract</option><option>Methods</option><option>Results</option><option>Discussion</option><option>Conclusion</option><option>Table or figure</option><option>Other</option></select>',
    ).replace(
        'Judgment</label><select id="label" required>',
        'Does the highlighted text support the claim?</label><span class="help">Choose only from this paper. “Insufficient” is correct when the paper does not answer the claim.</span><select id="label" required>',
    ).replace(
        'Claim as written</label><textarea id="claim" rows="3" required placeholder="Write one atomic claim to assess."></textarea>',
        'The single claim you are judging</label><span class="help">Keep it narrow. Do not add facts that are not in the paper.</span><textarea id="claim" rows="3" required placeholder="Example: The study reported a change in the measured outcome."></textarea>',
    ).replace(
        'Exact evidence quote</label><textarea id="quote" class="quote" readonly required placeholder="Select text in the source pane."></textarea>',
        'Exact text from the paper</label><span class="help">This fills automatically after you highlight text and click “Use selected evidence.”</span><textarea id="quote" class="quote" readonly required placeholder="Select text in the source pane."></textarea>',
    ).replace(
        'Actual study design</label><input id="design" required placeholder="e.g., controlled trial">',
        'What kind of study was this?</label><span class="help">Pick the closest description; choose “not clear” if needed.</span><select id="design" required><option value="">Choose study type…</option><option>prospective screening study</option><option>controlled trial</option><option>cohort study</option><option>observational study</option><option>cross-sectional study</option><option>case series</option><option>review</option><option>not clear from this paper</option></select>',
    ).replace(
        'Outcome assessed</label><input id="outcome" required placeholder="e.g., cognitive score">',
        'What outcome did they measure?</label><input id="outcome" required placeholder="e.g., cognitive score">',
    ).replace(
        'Causal interpretation</label><input id="causal" required placeholder="e.g., association only / causal support">',
        'What can the paper conclude?</label><span class="help">Most observational studies show an association, not cause and effect.</span><select id="causal" required><option value="">Choose conclusion type…</option><option>descriptive finding only</option><option>association only; no causal conclusion</option><option>causal support in the studied population</option><option>not assessable from this paper</option></select>',
    ).replace(
        'Limitations and reviewer notes</label><textarea id="notes" rows="3" placeholder="Scope limits, uncertainty, subgroup restrictions, or reason for insufficient."></textarea>',
        'Important limits or notes</label><textarea id="notes" rows="3" placeholder="Species, endpoint, sample, uncertainty, or why the evidence is insufficient."></textarea><div class="guide"><b>Remember:</b> dog evidence is not automatically cat evidence; a biomarker is not automatically a lifespan result; and an association is not automatically causal.</div>',
    ).replace(
        'Save draft entry</button><button id="download"',
        'Save this annotation</button><button id="download"',
    ).replace(
        'Download JSONL</button>',
        'Download my completed annotations</button>',
    ).replace(
        '<textarea id="source" readonly aria-label="Full paper source text"></textarea>',
        '<p class="guide"><b>Clean article body:</b> headings, paragraphs, and tables are shown. Journal metadata, affiliations, and references are omitted so you can focus on the evidence.</p><textarea id="source" readonly aria-label="Clean full paper article body"></textarea>',
    ).replace(
        '<span id="selection-status" class="small">Select exact evidence text, then capture it.</span><button id="capture" type="button">Use selected evidence</button>',
        '<span id="selection-status" class="small"><b>Step 2:</b> highlight the one sentence or table row that proves your claim.</span><button id="capture" type="button">Capture this evidence</button>',
    ).replace(
        '<div class="two"><div><label for="start">Start offset</label><input id="start" readonly></div><div><label for="end">End offset</label><input id="end" readonly></div></div>',
        '<div class="auto">✓ The evidence location is captured automatically. You do not need to count or edit anything.<input id="start" type="hidden" readonly><input id="end" type="hidden" readonly></div>',
    ).replace(
        '<option value="supported">Supported</option><option value="contradicted">Contradicted</option><option value="insufficient">Insufficient</option>',
        '<option value="supported">Yes — the exact text says this</option><option value="contradicted">No — the exact text conflicts with this</option><option value="insufficient">Not enough information in this paper</option>',
    ).replace(
        "Captured ${{b-a}} characters from the current paper.",
        "Evidence captured. Now complete the questions on the right, then save.",
    ).replace(
        "loadDrafts();render();",
        """function updateProgress(){const fields=[['reviewer','reviewer ID'],['claim','claim'],['quote','evidence'],['section','paper section'],['label','judgment'],['design','study type'],['outcome','outcome'],['causal','conclusion']];const missing=fields.filter(([id])=>!$('#'+id).value.trim()).map(([,label])=>label),done=fields.length-missing.length;$('#progress').textContent=missing.length?'Before saving ('+done+'/'+fields.length+' complete): add '+missing.slice(0,3).join(', ')+(missing.length>3?', and more.':''): '✓ Ready to save this finding.'}document.querySelectorAll('#form input,#form select,#form textarea').forEach(field=>{field.addEventListener('input',updateProgress);field.addEventListener('change',updateProgress)});$('#capture').addEventListener('click',()=>setTimeout(updateProgress));loadDrafts();render();updateProgress();""",
    )
    rendered = (template.replace("{{", "{").replace("}}", "}")
                .replace("__PAPER_COUNT__", html.escape(str(paper_count)))
                .replace("__PAYLOAD__", payload))
    return rendered.replace(
        "@media(max-width:700px){.how{grid-template-columns:1fr 1fr}</style>",
        "@media(max-width:700px){.how{grid-template-columns:1fr 1fr}}</style>",
    )
