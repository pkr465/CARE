// ---------------------------------------------------------------------------
// Module : memory_ctrl
// Description : Simplified memory controller — has timing and width issues
// ISSUES:
//   - Truncation warnings (addr width mismatch)
//   - Read-during-write behaviour undefined (no bypass logic)
//   - Uses integer type for counter (not synthesisable on all tools)
// ---------------------------------------------------------------------------
module memory_ctrl #(
    parameter ADDR_W = 10,
    parameter DATA_W = 32,
    parameter DEPTH  = 1024
)(
    input  logic               clk,
    input  logic               rst_n,
    input  logic               wr_en,
    input  logic               rd_en,
    input  logic [ADDR_W-1:0]  addr,
    input  logic [DATA_W-1:0]  wr_data,
    output logic [DATA_W-1:0]  rd_data,
    output logic               rd_valid
);

    logic [DATA_W-1:0] mem [0:DEPTH-1];

    // ISSUE: integer used as counter — some synthesis tools reject this
    integer i;

    // Write
    always_ff @(posedge clk) begin
        if (wr_en)
            mem[addr] <= wr_data;
    end

    // ISSUE: Read-during-write on same address — undefined behaviour
    // No write-first / read-first / no-change specification
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rd_data  <= '0;
            rd_valid <= 1'b0;
        end else if (rd_en) begin
            rd_data  <= mem[addr];
            rd_valid <= 1'b1;
        end else begin
            rd_valid <= 1'b0;
        end
    end

    // ISSUE: Initialisation loop using integer — simulation-only, not synthesisable
    initial begin
        for (i = 0; i < DEPTH; i = i + 1)
            mem[i] = '0;
    end

endmodule
