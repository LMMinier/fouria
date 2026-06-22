# FOURIA Corpus

Put allowed local reference material here:

- your own FL Studio notes
- your own beat breakdowns
- your own plugin-chain recipes
- open/licensed music theory notes
- exported production checklists

Use RAG for third-party manuals and copyrighted material unless you have explicit
permission to train on it.

## YouTube lessons

`scripts/ingest_youtube.py` accepts a video, playlist, or channel URL. It
temporarily downloads available English captions, generates original attributed
study notes with the local FOURIA model, and deletes the raw captions. Check the
creator's license/terms and only ingest material you are allowed to use. The
script strictly rejects videos unless metadata explicitly reports Creative
Commons, CC BY, CC0, or public-domain licensing.
