# Reverse Engineer Everything

## Frame the artifact

- Name the artifact exactly and draw its boundary before touching it. Write down what is inside the job (this binary, this page, this device, this listing) and what is outside it (the service behind it, the seller, the program it promotes).

- Write the question the work must answer, in the user's words. "How does it work" is not a question. "Where does the lead go after the form submits" is.

- Define what counts as understood before starting. A finished job names the parts, the interfaces between them, the data that flows, and the claims still unproven.

- Treat a shared name as a relationship, never an identity. A page named after a program is not the program, and a listing title is not the part inside the box. Read the thing itself.

## Inventory before theory

- Collect the raw evidence first and keep it verbatim. Use `muse.exec` for file identity, headers, strings and hashes on local files, `muse.read` for documents, and `browser.browse` for live pages so scripts, redirects and network calls are visible.

- Record where every fact came from as you collect it. A fact without a source becomes a guess three steps later.

- Prefer primary sources in this order. The artifact itself first, then its own source code, manual or datasheet, then the maker's documentation, then third party write-ups last and labeled as such.

- List what the artifact exposes before guessing what it hides. Entry points, files, ports, endpoints, fields, buttons, labels and error messages are the map's coastline.

## Map the structure

- Build the map as you go, in writing. Name each component, what it takes in, what it puts out, and what state it keeps.

- Follow one unit of data end to end through the map. A request, a file, a lead, a token or a payment traced completely teaches more than a broad skim of everything.

- Mark every edge on the map as observed, source stated or inferred. Inferred edges are hypotheses and get drawn dashed until a probe confirms them.

- Stop mapping when the user's question is answered or the remaining unknowns no longer change the decision. Say which point you stopped at.

## Probe the behavior

- Change one input at a time and watch what changes. Keep the probe small, repeatable and written down before running it.

- Compare against a known good reference when one exists. Two versions, two listings, two machines or the documented behavior make differences visible that a single sample hides.

- Read failure as evidence. An error message, a refused input or a missing field marks a real boundary of the system, so log it instead of routing around it silently.

- Work on a copy whenever the artifact can be damaged, billed or banned. Probe the original only when the copy cannot answer the question, and say so first.

## Label every claim

- Tag each finding with how it is known. Use measured for what a probe showed, source stated for what the maker documents, inferred for a reasoned conclusion and unknown for everything else.

- Never present an inference as a measurement. If a number did not come off the artifact or an instrument, it does not get stated as one.

- Keep the unknown list explicit and short. An unknown recorded honestly is a work item. An unknown papered over becomes a wrong fact in the next conversation.

- Recheck the claim that carries the decision. If the answer would change a purchase, a build or a message, verify that one claim a second way before reporting it.

## File the result

- Deliver the map, the evidence and the unknown list together. A verdict without its map cannot be checked later.

- File research results and discoveries where the system keeps them, using `muse.exec` with the Intel Bridge capture tool at ~/workspace/tools/bridge_dump.py for findings from a chat, and a research note under ~/workspace/research_notes/ for long form work.

- Register the work as a project when it will outlive the conversation, so the system can track and re-test it. A result left only in the transcript is a storage failure.

## Available connectors

- Use `muse.connector_search` to find other connectors and `muse.skill_search` to find related skills.

- If nothing here fits, look on the web for a maintained API or MCP server and set it up with [Custom Connectors and MCPs](/opt/muse/skills/custom-connector-setup/SKILL.md), or build a custom connector.

## Websites

- [MITRE ATT&CK](https://attack.mitre.org/) for naming adversary style techniques when the artifact is software behaving badly. Carry the observed behaviors into the page and match them there, never the other way around.

- [Vendor and maker documentation sites](https://www.intel.com/content/www/us/en/developer/articles/technical/software-security-guidance.html) for the primary source rule. Prefer the manual, datasheet or source repository for the exact artifact over any summary, and record the document name and date with the claim it supports.

## Alternatives for better results

- Ask for the one missing artifact detail that would unlock the identification when the evidence forks. A board revision, a file sample or an exact error string is worth more than a longer search.

- Reverse the smallest piece that answers the question first. A full teardown is a project, not a first move, and most decisions turn on one component or one data path.
