"""OpenTelemetry setup for Honeycomb."""

import logging
import os

from flask import Flask
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)


def configure_telemetry(app: Flask) -> None:
    api_key = os.environ.get("HONEYCOMB_API_KEY", "").strip()
    if not api_key:
        return

    service_name = os.environ.get("OTEL_SERVICE_NAME", "recipe-manager")
    resource = Resource.create({SERVICE_NAME: service_name})
    exporter = OTLPSpanExporter(
        endpoint="https://api.honeycomb.io/v1/traces",
        headers={"x-honeycomb-team": api_key},
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    FlaskInstrumentor().instrument_app(app)
    RequestsInstrumentor().instrument()

    logger.info("Honeycomb telemetry enabled for service: %s", service_name)
