workspace "LexBot Backend" {
  model {
    person User
    softwareSystem "LexBot Backend" {
      container "ApiGateway" "app.interface.api" "interface"
      container "AuthService" "app.application.auth" "application"
      container "IngestionService" "app.application.ingestion" "application"
      container "Indexer" "app.domain.indexer" "domain"
      container "SearchService" "app.domain.search" "domain"
      container "VectorStoreAdapter" "app.infrastructure.vectorstore" "infrastructure"
      container "BlobStorageAdapter" "app.infrastructure.blob" "infrastructure"
      "ApiGateway" -> "indexing-jobs" "consumes"
      "ApiGateway" -> "IngestionService" "calls"
      "Indexer" -> "indexing-jobs" "consumes"
      User -> "ApiGateway" ""
      "ApiGateway" -> "IngestionService" ""
      "IngestionService" -> "Indexer" ""
      "Indexer" -> "VectorStoreAdapter" ""
      "Indexer" -> "ApiGateway" ""
      "ApiGateway" -> "SearchService" ""
      "SearchService" -> "VectorStoreAdapter" ""
      "SearchService" -> "ApiGateway" ""
    }
  }
  views {
    container "LexBot Backend" {
      include *
      autoLayout
    }
  }
}
