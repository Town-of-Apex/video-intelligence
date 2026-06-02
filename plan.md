# Video Training Knowledge Assistant

## System Design Document (Prototype v1)

### Purpose

Provide a conversational AI interface for organizational training videos.

Users should be able to ask questions about training content and receive:

* Natural language answers
* Citations to relevant training materials
* Timestamp references
* Direct links to video locations (future phase)

Example:

Question:
"How do I submit a permit request?"

Answer:
"Permit requests are submitted through the Citizen Portal. The process begins by selecting New Application and choosing the permit category."

Sources:

* Permit Training Video (12:34-14:08)
* Permit Training Video (21:55-22:17)

---

# Goals

## Functional Goals

* Transcribe training videos
* Store transcripts and metadata
* Generate searchable embeddings
* Support semantic search
* Support conversational retrieval
* Return timestamp citations
* Support future video-link generation

## Non-Functional Goals

* Fully self-hosted
* Docker-based deployment
* Minimal licensing cost
* Modular architecture
* Ability to swap LLMs and embedding models

---

# High-Level Architecture

Video Files
↓

Transcription Service
(Faster-Whisper)

↓

Transcript Processor

↓

Chunking Pipeline

↓

Embedding Generator
(Ollama)

↓

PostgreSQL + pgvector

↓

Retrieval Service

↓

Ollama LLM

↓

Chat Interface

---

# Components

## 1. Video Ingestion

Purpose:
Accept training videos for processing.

Input:

* MP4
* MOV
* MKV

Metadata:

* Video title
* Department
* Training category
* Upload date
* Source URL (optional)

Storage:

/videos
/video_metadata

---

## 2. Transcription Service

Recommended Tool:
Faster-Whisper

Reasoning:

* Faster than OpenAI Whisper
* Lower memory requirements
* Excellent accuracy
* Local execution

Recommended Model:

Initial:
medium.en

Higher Accuracy:
large-v3

Output:

{
"start": 754.2,
"end": 767.8,
"text": "...",
"speaker": "unknown"
}

Future Enhancement:

Speaker diarization using:

* pyannote.audio

Optional for prototype.

---

## 3. Transcript Processor

Purpose:

Normalize transcript data.

Tasks:

* Remove transcription artifacts
* Merge extremely short segments
* Preserve timestamps
* Preserve speaker information

Output:

Structured transcript records

---

## 4. Chunking Service

Purpose:

Create retrieval-friendly text chunks.

Recommended Strategy:

Semantic chunking with overlap.

Target:

* 500–1000 words
* 15–30 second overlap

Store:

* chunk text
* chunk start timestamp
* chunk end timestamp

Example:

Chunk 142

Start:
12:34

End:
14:08

Text:
"To create a permit request..."

---

## 5. Embedding Service

Recommended Tool:

Ollama

Recommended Models:

nomic-embed-text

Alternative:

bge-large

Process:

Chunk Text
↓

Embedding Vector
↓

Store in pgvector

---

## 6. Database Layer

Database:
PostgreSQL

Extension:
pgvector

Tables:

videos

* id
* title
* category
* upload_date
* source_url

transcript_segments

* id
* video_id
* start_time
* end_time
* speaker
* text

chunks

* id
* video_id
* start_time
* end_time
* text
* embedding

---

# Retrieval Pipeline

User Question

↓

Generate Embedding

↓

Vector Search

↓

Top Relevant Chunks

↓

Prompt Construction

↓

Ollama LLM

↓

Answer + Citations

---

# Citation System

Every retrieved chunk contains:

* video_id
* start_time
* end_time

Response format:

Answer Text

Sources:

Permit Training
12:34-14:08

Future URL Generation:

Base URL

https://training.example.gov/video/15

Generated Link

https://training.example.gov/video/15?t=754

---

# Summarization Layer (Recommended)

After transcription:

Generate:

* Video summary
* Section summaries
* Keywords

Store separately.

Benefits:

* Improved retrieval
* Better search quality
* Reduced hallucinations

Tables:

video_summaries

section_summaries

---

# API Layer

Framework:

FastAPI

Endpoints:

POST /videos

Upload video

POST /process

Run transcription pipeline

POST /chat

Ask questions

GET /video/{id}

Retrieve metadata

---

# Docker Services

docker-compose

Services:

postgres
pgvector enabled

ollama

transcription-worker

api

frontend (future)

---

# Future Enhancements

Phase 2

* Speaker diarization
* Clickable timestamp links
* Multi-video conversations
* Department-specific collections

Phase 3

* Hybrid search (vector + keyword)
* Permissions model
* SharePoint integration
* Automatic training catalog generation

Phase 4

* Training content recommendations
* Auto-generated FAQs
* Knowledge gap analysis
* Training effectiveness reporting

---

# Recommended Technology Stack

Transcription:
Faster-Whisper

Speaker Recognition:
pyannote.audio

Backend:
Python

API:
FastAPI

Database:
PostgreSQL + pgvector

Vector Search:
pgvector

LLM:
Ollama

Embedding Model:
nomic-embed-text

Containerization:
Docker Compose

Reverse Proxy:
Nginx

Authentication:
Microsoft Entra ID (future)
