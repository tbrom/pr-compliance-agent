from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
import logging

logger = logging.getLogger("sentinel.telemetry")

def setup_telemetry():
    try:
        provider = TracerProvider()
        
        # Push traces asynchronously to Google Cloud Trace
        exporter = CloudTraceSpanExporter()
        processor = BatchSpanProcessor(exporter)
        
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
    except Exception as e:
        logger.warning(f"Failed to setup Cloud Trace (this is normal locally without GCP ADC): {e}")
