workspace "Remote Server" {
  model {
    person User
    softwareSystem "Remote Server" {
      container "ApiGateway" "app.interface.api" "interface"
      container "AuthService" "app.application.auth" "application"
      container "RateLimiter" "app.application.ratelimit" "application"
      container "IngestionService" "app.application.ingestion" "application"
      container "MetadataService" "app.domain.metadata" "domain"
      container "Indexer" "app.domain.indexer" "domain"
      container "SearchService" "app.domain.search" "domain"
      container "ChatService" "app.domain.chat" "domain"
      container "VectorStoreAdapter" "app.infrastructure.vectorstore" "infrastructure"
      container "EmbeddingAdapter" "app.infrastructure.embedding" "infrastructure"
      container "LLMAdapter" "app.infrastructure.llm" "infrastructure"
      container "BlobStorageAdapter" "app.infrastructure.blob" "infrastructure"
      "ApiGateway" -> "IngestionService" "calls"
      "Indexer" -> "ingestion-jobs" "consumes"
      "ApiGateway" -> "ChatService" "calls"
      User -> "ApiGateway" "POST /v1/files (Bearer)"
      "ApiGateway" -> "AuthService" "validateToken"
      "ApiGateway" -> "IngestionService" "validate+checksum+persist → emit IndexJob"
      "IngestionService" -> "Indexer" "enqueue(IndexJob)"
      "Indexer" -> "MetadataService" "generateMetadata(file_id)"
      "Indexer" -> "EmbeddingAdapter" "embed(chunks)"
      "Indexer" -> "VectorStoreAdapter" "upsert(vectors@tenant)"
      "Indexer" -> "ApiGateway" "event: jobs(IndexResult)"
      User -> "ApiGateway" "GET /v1/search?q"
      "ApiGateway" -> "SearchService" "search(q, limit, tenant)"
      "SearchService" -> "VectorStoreAdapter" "query(knn @tenant)"
      "SearchService" -> "ApiGateway" "return SearchResults"
      User -> "ApiGateway" "POST /v1/chat (message, stream?)"
      "ApiGateway" -> "ChatService" "chat(ChatRequest)"
      "ChatService" -> "SearchService" "retrieve top-k for grounding"
      "ChatService" -> "LLMAdapter" "synthesize answer (prompt+context)"
      "ChatService" -> "ApiGateway" "ChatResponse (or WS stream)"
    }
  }
  views {
    container "Remote Server" {
      include *
      autoLayout
    }
  }
}
