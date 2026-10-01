from fastapi import Request


def get_config(request: Request):
    return request.app.state.config


def get_db(request: Request):
    return request.app.state.db


def get_doc_processor(request: Request):
    return request.app.state.doc_processor


def get_vector_store(request: Request):
    return request.app.state.vector_store


def get_rag_system(request: Request):
    return request.app.state.rag_system
