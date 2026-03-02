// ---------------------------------------------------------------------------
// Module : fifo_sync
// Description : Parameterised synchronous FIFO — clean reference design
// ---------------------------------------------------------------------------
module fifo_sync #(
    parameter DATA_WIDTH = 8,
    parameter DEPTH      = 16,
    parameter ADDR_WIDTH = $clog2(DEPTH)
)(
    input  wire                   clk,
    input  wire                   rst_n,
    input  wire                   wr_en,
    input  wire [DATA_WIDTH-1:0]  wr_data,
    input  wire                   rd_en,
    output reg  [DATA_WIDTH-1:0]  rd_data,
    output wire                   full,
    output wire                   empty,
    output reg  [ADDR_WIDTH:0]    count
);

    reg [DATA_WIDTH-1:0] mem [0:DEPTH-1];
    reg [ADDR_WIDTH-1:0] wr_ptr;
    reg [ADDR_WIDTH-1:0] rd_ptr;

    assign full  = (count == DEPTH);
    assign empty = (count == 0);

    // Write logic
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wr_ptr <= {ADDR_WIDTH{1'b0}};
        end else if (wr_en && !full) begin
            mem[wr_ptr] <= wr_data;
            wr_ptr      <= wr_ptr + 1'b1;
        end
    end

    // Read logic
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rd_ptr  <= {ADDR_WIDTH{1'b0}};
            rd_data <= {DATA_WIDTH{1'b0}};
        end else if (rd_en && !empty) begin
            rd_data <= mem[rd_ptr];
            rd_ptr  <= rd_ptr + 1'b1;
        end
    end

    // Count tracker
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            count <= {(ADDR_WIDTH+1){1'b0}};
        end else begin
            case ({wr_en && !full, rd_en && !empty})
                2'b10  : count <= count + 1'b1;
                2'b01  : count <= count - 1'b1;
                default: count <= count;
            endcase
        end
    end

endmodule
