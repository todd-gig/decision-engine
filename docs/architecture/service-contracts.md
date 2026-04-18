# Service Contracts

## capture-service
Input: capture session create payload
Output: normalized capture session record

## memory-service
Input: normalized context unit
Output: stored memory record with importance score

## orchestration-service
Input: workflow request + input refs
Output: workflow run state + emitted events

## trust-service
Input: evidence set
Output: trust score + rationale

## artifact-service
Input: source refs + sections + artifact type
Output: artifact manifest and export-ready package metadata
