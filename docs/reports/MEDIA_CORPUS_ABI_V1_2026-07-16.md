# MEDIA-CORPUS-ABI-V1

Date: 2026-07-16
Status: intake contract, not runtime admission

## Purpose

Define the intake contract for high-quality combat media that may benefit Just Dodge.

## Rule

All combat media enters as offline corpus evidence only.
It may become training data, constraints, evaluation fixtures, or proposal references.
It may never become runtime animation playback.

## Schema

Canonical schema file:
`assets/data/media_corpus_abi_v1.schema.json`

## Required fields

- schema_version
- record_id
- source
- rights
- media
- skeleton
- coordinate
- labels
- qa
- admission

## Admission rule

`admission.runtime_allowed` is always `false` in v1.
`training_allowed` may be true only after provenance review.

## Immediate source classes to ingest aggressively

- anime/film combat clips
- anime/film combat images
- anime/film combat videos
- sakuga and production reference material
- mocap and movement datasets
- user-owned media
- any high-quality combat source that can improve MotionBricks conditioning, evaluation, or proposal quality

## Boundary

Do not wire corpus media into runtime assets, primitive lookup, or baked playback paths.
