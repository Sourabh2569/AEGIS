# ADR 0049: Broker Order Access Remains Disabled

Data Activation does not introduce broker order access, funds, holdings, order status, or execution APIs. `BROKER_ORDER_ACCESS=false` and `LIVE_EXECUTION_ENABLED=false` remain hard startup guards.
