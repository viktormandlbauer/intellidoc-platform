# Extraction
* https://github.com/docling-project/docling
* https://github.com/tesseract-ocr/tesseract

# Classification
* https://github.com/NandhaKishorM/laya
* https://github.com/scikit-learn/scikit-learn
* https://github.com/pytorch/pytorch

# API
* https://github.com/fastapi/fastapi

# Conversion (optional, for later use)
* https://github.com/gotenberg/gotenberg

# Storage & Search
* https://github.com/postgres/postgres
* https://github.com/pgvector/pgvector

# Architecture

```mermaid
flowchart LR
    subgraph Input
        GOT["Gotenberg<br/>optional, not wired"]
        CLI["intellidoc CLI<br/>classify · sort · index · search"]
        API["FastAPI :8080<br/>/classify · /classify-text"]
    end

    subgraph Extraction
        DOC["Docling<br/>text layer, first 3 pages"]
        OCR["Docling + Tesseract<br/>full-page OCR, deu+eng"]
    end

    subgraph Classification
        HF[("Hugging Face<br/>Laya checkpoints")]
        LAYA["Laya · PyTorch<br/>zero-shot, all questions"]
        MLP["scikit-learn MLP<br/>trained, primary label"]
        HYB["Hybrid<br/>combine: ml or average"]
    end

    GATE{"Confidence gate<br/>auto · review · error"}

    subgraph Output
        OUT["JSON / CSV"]
        SORT["Sorted folders<br/>sorted/label/ · _review/"]
        PG[("PostgreSQL<br/>full-text search, jsonb answers")]
        VEC["pgvector<br/>embeddings, not wired"]
    end

    subgraph Loop["Learning loop"]
        REV["Human review<br/>intellidoc review"]
        LAB["labelled/label/*.pdf"]
        TRAIN["intellidoc train"]
        PKL[("classifier.pkl")]
    end

    GOT -. "Office → PDF" .-> CLI
    CLI -- PDF --> DOC
    API -- PDF --> DOC
    DOC -- "< 50 chars" --> OCR
    DOC -- text --> LAYA
    DOC -- text --> MLP
    OCR -- text --> LAYA
    OCR -- text --> MLP
    HF -- "~1 GB, first run" --> LAYA
    LAYA --> HYB
    MLP --> HYB
    HYB --> GATE
    GATE --> OUT
    GATE --> SORT
    GATE --> PG
    PG -. "kNN, later" .- VEC
    CLI -- "search" --> PG

    REV -- "sets review_label" --> PG
    PG -- "reviewed docs" --> TRAIN
    LAB -- PDFs --> TRAIN
    TRAIN -- writes --> PKL
    PKL -- "reloaded on change" --> MLP

    classDef optional stroke-dasharray: 5 5
    class GOT,VEC optional
```

`classification.backend` (or `--backend`) selects Laya alone, the trained MLP alone, or Hybrid (the MLP sets the label; Laya answers the yes/no and score questions).
