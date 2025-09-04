  from fastapi import FastAPI
  from components.ratelimiter.app import router as ratelimiter_router

  app = FastAPI()
  app.include_router(ratelimiter_router)