// ---------------------------------------------------------------------------
// Module : reset_issues
// Description : Reset-related design flaws
// BUG LIST:
//   1. Mixed reset polarity (active-high vs active-low in same design)
//   2. Async reset used on some flops, sync on others (inconsistent)
//   3. Reset signal used combinationally (glitch risk)
//   4. Missing reset on stateful register
// ---------------------------------------------------------------------------
module reset_issues (
    input  wire       clk,
    input  wire       rst_n,     // active-low
    input  wire       rst,       // active-high
    input  wire [7:0] data_in,
    output reg  [7:0] reg_a,
    output reg  [7:0] reg_b,
    output reg  [7:0] reg_c,
    output reg  [7:0] reg_d,
    output wire [7:0] combo_out
);

    // BUG 1: Active-low reset here
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            reg_a <= 8'h00;
        else
            reg_a <= data_in;
    end

    // BUG 1 continued: Active-high reset in the same module — inconsistent
    always @(posedge clk or posedge rst) begin
        if (rst)
            reg_b <= 8'h00;
        else
            reg_b <= data_in + 8'h01;
    end

    // BUG 2: Synchronous reset — mixed with async above
    always @(posedge clk) begin
        if (!rst_n)
            reg_c <= 8'h00;
        else
            reg_c <= reg_a ^ reg_b;
    end

    // BUG 3: Reset used in combinational logic — glitch-prone
    assign combo_out = rst_n ? (reg_a + reg_b) : 8'h00;

    // BUG 4: No reset at all — reg_d powers up in unknown state
    always @(posedge clk) begin
        reg_d <= reg_c + reg_a;
    end

endmodule
