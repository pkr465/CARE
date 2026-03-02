// ---------------------------------------------------------------------------
// Module : cdc_violation
// Description : Intentional CDC bugs — signals crossing clock domains
//               without proper synchronisation
// BUG LIST:
//   1. req_sync   — single-flop synchroniser (needs 2-flop)
//   2. data_bus   — multi-bit CDC with no gray-coding or handshake
//   3. ack_pulse  — combinational path across domains (no flop at all)
// ---------------------------------------------------------------------------
module cdc_violation (
    input  wire       clk_a,
    input  wire       clk_b,
    input  wire       rst_n,
    // Domain A
    input  wire       req_a,
    input  wire [7:0] data_a,
    // Domain B
    output reg        req_b,
    output reg  [7:0] data_b,
    output wire       ack_pulse
);

    // BUG 1: Single-flop synchroniser — metastability risk
    // Should be a 2-flop (or 3-flop) synchroniser chain
    always @(posedge clk_b or negedge rst_n) begin
        if (!rst_n)
            req_b <= 1'b0;
        else
            req_b <= req_a;  // ← only one flop!
    end

    // BUG 2: Multi-bit bus crossing without gray code or handshake
    // All 8 bits can arrive at different meta-stable states
    always @(posedge clk_b or negedge rst_n) begin
        if (!rst_n)
            data_b <= 8'b0;
        else
            data_b <= data_a;  // ← raw multi-bit CDC!
    end

    // BUG 3: Purely combinational path across domains — no register
    assign ack_pulse = req_a & req_b;  // ← glitch-prone, no sync

endmodule
