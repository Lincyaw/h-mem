import { GraphQLClient, gql } from "graphql-request";

// Build absolute URL for GraphQL endpoint
const getGraphQLUrl = (): string => {
  if (typeof window !== "undefined") {
    return `${window.location.origin}/graphql`;
  }
  // Fallback for SSR/testing
  return "http://localhost:8080/graphql";
};

export const client = new GraphQLClient(getGraphQLUrl());

// ===== Types =====

export type NodeType =
  | "CONVERSATION"
  | "FACT"
  | "PRINCIPLE"
  | "SKILL"
  | "ENTITY"
  | "PROCESS";
export type Direction = "IN" | "OUT" | "BOTH";

export interface GraphNode {
  id: string;
  nodeType: NodeType;
  label: string;
  qValue: number | null;
  isDeprecated: boolean;
}

export interface GraphEdge {
  source: string;
  target: string;
  relationship: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  hasMore: boolean;
}

export interface ConversationNode {
  __typename: "ConversationNode";
  id: string;
  nodeType: NodeType;
  sessionId: string;
  createdAt: string;
  metadataJson: string | null;
}

export interface FactNode {
  __typename: "FactNode";
  id: string;
  nodeType: NodeType;
  entityId: string | null;
  slot: string | null;
  value: string | null;
  cardinality: string | null;
  version: number;
  isSuperseded: boolean;
  createdAt: string;
  updatedAt: string | null;
  sourceRole: string | null;
  importance: number | null;
  confidence: number | null;
  qValue: number;
  qUpdateCount: number;
}

export interface PrincipleNode {
  __typename: "PrincipleNode";
  id: string;
  nodeType: NodeType;
  content: string;
  evidenceCount: number;
  confidence: number;
  createdAt: string;
  isDeprecated: boolean;
  version: number;
  qValue: number;
  qUpdateCount: number;
}

export interface SkillNode {
  __typename: "SkillNode";
  id: string;
  nodeType: NodeType;
  name: string;
  triggerPattern: string | null;
  description: string | null;
  actionTemplate: string | null;
  tags: string[] | null;
  createdAt: string;
  updatedAt: string | null;
  isDeprecated: boolean;
  version: number;
  qValue: number;
  qUpdateCount: number;
}

export interface EntityNode {
  __typename: "EntityNode";
  id: string;
  nodeType: NodeType;
  canonicalName: string;
  aliases: string[] | null;
  entityType: string;
  needsResolution: boolean;
  createdAt: string;
  updatedAt: string | null;
}

export interface ProcessNode {
  __typename: "ProcessNode";
  id: string;
  nodeType: NodeType;
  trigger: string;
  action: string;
  outcome: string | null;
  confidence: number;
  isDeprecated: boolean;
  createdAt: string;
  updatedAt: string | null;
  qValue: number;
  qUpdateCount: number;
}

export type Node =
  | ConversationNode
  | FactNode
  | PrincipleNode
  | SkillNode
  | EntityNode
  | ProcessNode;

export interface Stats {
  conversations: number;
  entities: number;
  facts: number;
  active_facts: number;
  principles: number;
  active_principles: number;
  skills: number;
  active_skills: number;
  processes: number;
  active_processes: number;
}

// ===== Queries =====

const SEARCH_QUERY = gql`
  query Search($query: String!, $types: [NodeType!], $limit: Int) {
    search(query: $query, types: $types, limit: $limit) {
      __typename
      ... on ConversationNode {
        id
        nodeType
        sessionId
        createdAt
      }
      ... on FactNode {
        id
        nodeType
        entityId
        slot
        value
        cardinality
        version
        isSuperseded
        createdAt
        qValue
        qUpdateCount
      }
      ... on PrincipleNode {
        id
        nodeType
        content
        evidenceCount
        confidence
        createdAt
        isDeprecated
        version
        qValue
        qUpdateCount
      }
      ... on SkillNode {
        id
        nodeType
        name
        description
        tags
        createdAt
        isDeprecated
        version
        qValue
        qUpdateCount
      }
      ... on EntityNode {
        id
        nodeType
        canonicalName
        aliases
        entityType
        needsResolution
        createdAt
      }
      ... on ProcessNode {
        id
        nodeType
        trigger
        action
        outcome
        confidence
        isDeprecated
        createdAt
        qValue
        qUpdateCount
      }
    }
  }
`;

const EXPAND_QUERY = gql`
  query Expand($nodeId: ID!, $direction: Direction, $depth: Int) {
    expand(nodeId: $nodeId, direction: $direction, depth: $depth) {
      nodes {
        id
        nodeType
        label
        qValue
        isDeprecated
      }
      edges {
        source
        target
        relationship
      }
      hasMore
    }
  }
`;

const NODE_DETAIL_QUERY = gql`
  query NodeDetail($nodeId: ID!) {
    nodeDetail(nodeId: $nodeId) {
      __typename
      ... on ConversationNode {
        id
        nodeType
        sessionId
        createdAt
        metadataJson
      }
      ... on FactNode {
        id
        nodeType
        entityId
        slot
        value
        cardinality
        version
        isSuperseded
        createdAt
        updatedAt
        sourceRole
        importance
        confidence
        qValue
        qUpdateCount
      }
      ... on PrincipleNode {
        id
        nodeType
        content
        evidenceCount
        confidence
        createdAt
        isDeprecated
        version
        qValue
        qUpdateCount
      }
      ... on SkillNode {
        id
        nodeType
        name
        triggerPattern
        description
        actionTemplate
        tags
        createdAt
        updatedAt
        isDeprecated
        version
        qValue
        qUpdateCount
      }
      ... on EntityNode {
        id
        nodeType
        canonicalName
        aliases
        entityType
        needsResolution
        createdAt
        updatedAt
      }
      ... on ProcessNode {
        id
        nodeType
        trigger
        action
        outcome
        confidence
        isDeprecated
        createdAt
        updatedAt
        qValue
        qUpdateCount
      }
    }
  }
`;

const LINEAGE_QUERY = gql`
  query Lineage($nodeId: ID!, $maxDepth: Int) {
    lineage(nodeId: $nodeId, maxDepth: $maxDepth) {
      __typename
      ... on ConversationNode {
        id
        nodeType
        sessionId
        createdAt
      }
      ... on FactNode {
        id
        nodeType
        entityId
        slot
        value
        createdAt
        qValue
      }
      ... on PrincipleNode {
        id
        nodeType
        content
        createdAt
        qValue
      }
      ... on SkillNode {
        id
        nodeType
        name
        createdAt
        qValue
      }
      ... on EntityNode {
        id
        nodeType
        canonicalName
        entityType
        createdAt
      }
      ... on ProcessNode {
        id
        nodeType
        trigger
        action
        createdAt
        qValue
      }
    }
  }
`;

const STATS_QUERY = gql`
  query Stats {
    stats
  }
`;

// ===== Mutations =====

const UPDATE_NODE_MUTATION = gql`
  mutation UpdateNode(
    $nodeId: ID!
    $nodeType: NodeType!
    $input: NodeUpdateInput!
  ) {
    updateNode(nodeId: $nodeId, nodeType: $nodeType, input: $input) {
      __typename
      ... on FactNode {
        id
        qValue
      }
      ... on PrincipleNode {
        id
        qValue
        isDeprecated
      }
      ... on SkillNode {
        id
        qValue
        isDeprecated
      }
      ... on ProcessNode {
        id
        qValue
        isDeprecated
      }
    }
  }
`;

const DEPRECATE_NODE_MUTATION = gql`
  mutation DeprecateNode($nodeId: ID!, $reason: String!) {
    deprecateNode(nodeId: $nodeId, reason: $reason)
  }
`;

// ===== API Functions =====

export async function search(
  query: string,
  types?: NodeType[],
  limit?: number
): Promise<Node[]> {
  const result = await client.request<{ search: Node[] }>(SEARCH_QUERY, {
    query,
    types,
    limit,
  });
  return result.search;
}

export async function expand(
  nodeId: string,
  direction: Direction = "BOTH",
  depth: number = 1
): Promise<GraphData> {
  const result = await client.request<{ expand: GraphData }>(EXPAND_QUERY, {
    nodeId,
    direction,
    depth,
  });
  return result.expand;
}

export async function getNodeDetail(nodeId: string): Promise<Node | null> {
  const result = await client.request<{ nodeDetail: Node | null }>(
    NODE_DETAIL_QUERY,
    { nodeId }
  );
  return result.nodeDetail;
}

export async function getLineage(
  nodeId: string,
  maxDepth: number = 5
): Promise<Node[]> {
  const result = await client.request<{ lineage: Node[] }>(LINEAGE_QUERY, {
    nodeId,
    maxDepth,
  });
  return result.lineage;
}

export async function getStats(): Promise<Stats> {
  const result = await client.request<{ stats: Stats }>(STATS_QUERY);
  return result.stats;
}

export async function updateNode(
  nodeId: string,
  nodeType: NodeType,
  input: { qValue?: number; isDeprecated?: boolean; weight?: number }
): Promise<Node | null> {
  const result = await client.request<{ updateNode: Node | null }>(
    UPDATE_NODE_MUTATION,
    { nodeId, nodeType, input }
  );
  return result.updateNode;
}

export async function deprecateNode(
  nodeId: string,
  reason: string
): Promise<boolean> {
  const result = await client.request<{ deprecateNode: boolean }>(
    DEPRECATE_NODE_MUTATION,
    { nodeId, reason }
  );
  return result.deprecateNode;
}

// List nodes by type (for Browse mode)
const LIST_BY_TYPE_QUERY = gql`
  query ListByType($nodeType: NodeType!, $limit: Int) {
    listByType(nodeType: $nodeType, limit: $limit) {
      __typename
      ... on ConversationNode {
        id
        nodeType
        sessionId
        createdAt
      }
      ... on FactNode {
        id
        nodeType
        entityId
        slot
        value
        cardinality
        version
        isSuperseded
        createdAt
        qValue
        qUpdateCount
      }
      ... on PrincipleNode {
        id
        nodeType
        content
        evidenceCount
        confidence
        createdAt
        isDeprecated
        version
        qValue
        qUpdateCount
      }
      ... on SkillNode {
        id
        nodeType
        name
        description
        tags
        createdAt
        isDeprecated
        version
        qValue
        qUpdateCount
      }
      ... on EntityNode {
        id
        nodeType
        canonicalName
        aliases
        entityType
        needsResolution
        createdAt
      }
      ... on ProcessNode {
        id
        nodeType
        trigger
        action
        outcome
        confidence
        isDeprecated
        createdAt
        qValue
        qUpdateCount
      }
    }
  }
`;

export async function listByType(
  nodeType: NodeType,
  limit: number = 50
): Promise<Node[]> {
  const result = await client.request<{ listByType: Node[] }>(LIST_BY_TYPE_QUERY, {
    nodeType,
    limit,
  });
  return result.listByType;
}
