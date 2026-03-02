// ---------------------------------------------------------------------------
// Module : counter_gray
// Description : Parameterised Gray-code counter — useful for async FIFOs
//               Clean, synthesisable reference
// ---------------------------------------------------------------------------
module counter_gray #(
    parameter WIDTH = 4
)(
    input  logic              clk,
    input  logic              rst_n,
    input  logic              enable,
    output logic [WIDTH-1:0]  gray_out,
    output logic [WIDTH-1:0]  binary_out
);

    logic [WIDTH-1:0] binary_cnt;

    // Binary counter
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            binary_cnt <= '0;
        else if (enable)
            binary_cnt <= binary_cnt + 1'b1;
    end

    // Binary-to-Gray conversion
    assign binary_out = binary_cnt;
    assign gray_out   = binary_cnt ^ (binary_cnt >> 1);

endmodule
