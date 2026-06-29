FROM python:3.11-slim

WORKDIR /app

# Install system dependencies needed for compiling or running certain packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Jupyter Kernel Gateway, ipykernel, and essential data science packages
RUN pip install --no-cache-dir \
    jupyter_kernel_gateway \
    ipykernel \
    matplotlib \
    numpy \
    pandas \
    scipy

# Create a non-root user for sandbox isolation
RUN useradd -u 1000 -m jovyan

# Create shared output directory and set ownership to jovyan
RUN mkdir -p /tmp/outputs && chown -R jovyan:jovyan /tmp/outputs

USER jovyan

# Register the python3 kernel spec for the jovyan user
RUN python -m ipykernel install --user

# Run the kernel gateway on port 8888 without authentication token for ease of internal use
CMD ["jupyter", "kernelgateway", "--KernelGatewayApp.ip=0.0.0.0", "--KernelGatewayApp.port=8888", "--KernelGatewayApp.auth_token="]
