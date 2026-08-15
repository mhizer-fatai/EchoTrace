"""
OpenCypher queries for HydraDB graph operations
"""

# Insert or update an agent node
UPSERT_AGENT = """
MERGE (a:Agent {id: $id})
SET a.label = $label,
    a.agent_name = $agent_name,
    a.role = $role,
    a.framework = $framework,
    a.session_id = $session_id,
    a.created_at = $created_at
RETURN a
"""

# Insert a fact node
INSERT_FACT = """
CREATE (f:Fact {
    id: $id,
    label: $label,
    entity: $entity,
    property_name: $property_name,
    property_value: $property_value,
    status: $status,
    confidence: $confidence,
    source_agent_id: $source_agent_id,
    session_id: $session_id,
    created_at: $created_at,
    valid_from: $valid_from,
    valid_to: $valid_to
})
RETURN f
"""

# Insert evidence node and link to fact
INSERT_EVIDENCE_LINK = """
CREATE (e:Evidence {
    id: $id,
    label: $label,
    source_uri: $source_uri,
    content_snippet: $content_snippet,
    verified: $verified,
    session_id: $session_id,
    created_at: $created_at
})
WITH e
MATCH (f:Fact {id: $fact_id})
CREATE (f)-[:SUPPORTED_BY]->(e)
RETURN e
"""

# Insert a decision node
INSERT_DECISION = """
CREATE (d:Decision {
    id: $id,
    label: $label,
    agent_id: $agent_id,
    action_type: $action_type,
    rationale: $rationale,
    is_stale: $is_stale,
    session_id: $session_id,
    created_at: $created_at
})
RETURN d
"""

# Insert artifact node
INSERT_ARTIFACT = """
CREATE (art:Artifact {
    id: $id,
    label: $label,
    artifact_name: $artifact_name,
    content: $content,
    artifact_type: $artifact_type,
    is_stale: $is_stale,
    session_id: $session_id,
    created_at: $created_at
})
RETURN art
"""

# Create relationship edge between two nodes
CREATE_EDGE = """
MATCH (source {id: $source_id})
MATCH (target {id: $target_id})
CREATE (source)-[r:RELATIONSHIP {id: $edge_id, edge_type: $edge_type, created_at: $created_at}]->(target)
RETURN r
"""

# Multi-hop downstream blast radius traversal
# Finds all decisions, artifacts, and tool calls that depend on an invalidated fact
BLAST_RADIUS_DOWNSTREAM = """
MATCH path = (f:Fact {id: $fact_id})<-[:DEPENDS_ON|PRODUCED|TRIGGERED*1..15]-(downstream)
WHERE downstream.session_id = $session_id
RETURN downstream, [rel in relationships(path) | type(rel)] as rel_types, nodes(path) as path_nodes
"""

# Historical snapshot query at a specific point in time
TEMPORAL_SNAPSHOT_NODES = """
MATCH (n)
WHERE n.session_id = $session_id
  AND n.valid_from <= $snapshot_time
  AND (n.valid_to IS NULL OR n.valid_to > $snapshot_time)
RETURN n
"""

# Fetch full session graph
GET_FULL_SESSION_GRAPH = """
MATCH (n {session_id: $session_id})
OPTIONAL MATCH (n)-[r]->(m {session_id: $session_id})
RETURN collect(DISTINCT n) as nodes, collect(DISTINCT r) as edges
"""

# Mark a fact as invalidated and update valid_to timestamp
INVALIDATE_FACT = """
MATCH (f:Fact {id: $fact_id})
SET f.status = 'INVALIDATED',
    f.valid_to = $invalidated_at
RETURN f
"""

# Mark a fact as superseded by a new fact
SUPERSEDE_FACT = """
MATCH (old_fact:Fact {id: $old_fact_id})
MATCH (new_fact:Fact {id: $new_fact_id})
SET old_fact.status = 'SUPERSEDED',
    old_fact.valid_to = $timestamp
CREATE (old_fact)-[:SUPERSEDED_BY {created_at: $timestamp}]->(new_fact)
RETURN old_fact, new_fact
"""

# Query for potential contradictory facts on the same entity and property
FIND_CONTRADICTIONS = """
MATCH (f1:Fact {session_id: $session_id, status: 'VALID'})
MATCH (f2:Fact {session_id: $session_id, status: 'VALID'})
WHERE f1.entity = f2.entity
  AND f1.property_name = f2.property_name
  AND f1.property_value <> f2.property_value
  AND id(f1) < id(f2)
RETURN f1, f2
"""
