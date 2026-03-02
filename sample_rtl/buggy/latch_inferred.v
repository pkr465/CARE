// ---------------------------------------------------------------------------
// Module : latch_inferred
// Description : Intentional latch-inference bugs from incomplete
//               sensitivity lists and missing default/else branches
// BUG LIST:
//   1. result_a  — incomplete case (no default) infers latch
//   2. result_b  — missing else branch infers latch
//   3. mux_out   — incomplete sensitivity list (Verilog-95 style)
// ---------------------------------------------------------------------------
module latch_inferred (
    input  wire [1:0] sel,
    input  wire [7:0] in_a,
    input  wire [7:0] in_b,
    input  wire [7:0] in_c,
    input  wire       enable,
    output reg  [7:0] result_a,
    output reg  [7:0] result_b,
    output reg  [7:0] mux_out
);

    // BUG 1: Incomplete case — missing sel==2'b11 and no default
    // Synthesis will infer a latch to hold result_a when sel==2'b11
    always @(*) begin
        case (sel)
            2'b00 : result_a = in_a;
            2'b01 : result_b = in_b;  // ← also assigns wrong register
            2'b10 : result_a = in_c;
            // no default!
        endcase
    end

    // BUG 2: Missing else — when enable==0, result_b retains its value
    always @(*) begin
        if (enable)
            result_b = in_a + in_b;
        // no else → latch inferred for result_b
    end

    // BUG 3: Incomplete sensitivity list (old Verilog-95 style)
    // Missing in_b and sel from the list
    always @(in_a) begin
        case (sel)
            2'b00 : mux_out = in_a;
            2'b01 : mux_out = in_b;
            default: mux_out = 8'b0;
        endcase
    end

endmodule
