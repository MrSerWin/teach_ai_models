# Reference image for training inside a container instead of a cloned conda env.
# Pin the PyTorch base you need — this tag exists on nvcr.io and dockerhub.
# Swap for pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime if you prefer dockerhub.
ARG PYTORCH_IMAGE=pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime
FROM ${PYTORCH_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      git tini ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Common ML deps. Override/extend in your experiment's own Dockerfile if needed.
RUN pip install --upgrade pip && pip install \
      pyyaml pandas numpy pillow scikit-learn tqdm tensorboard

WORKDIR /workspace
ENTRYPOINT ["tini", "--"]
CMD ["bash"]
