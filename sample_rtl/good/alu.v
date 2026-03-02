// ---------------------------------------------------------------------------
// Module : alu
// Description : Simple 8-bit ALU — clean, synthesisable reference design
// ---------------------------------------------------------------------------
module alu (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [7:0]  operand_a,
    input  wire [7:0]  operand_b,
    input  wire [2:0]  op_sel,
    output reg  [8:0]  result,
    output reg         zero_flag,
    output reg         overflow_flag
);

    localparam OP_ADD  = 3'b000;
    localparam OP_SUB  = 3'b001;
    localparam OP_AND  = 3'b010;
    localparam OP_OR   = 3'b011;
    localparam OP_XOR  = 3'b100;
    localparam OP_SHL  = 3'b101;
    localparam OP_SHR  = 3'b110;
    localparam OP_NOP  = 3'b111;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            result        <= 9'b0;
            zero_flag     <= 1'b0;
            overflow_flag <= 1'b0;
        end else begin
            case (op_sel)
                OP_ADD : result <= {1'b0, operand_a} + {1'b0, operand_b};
                OP_SUB : result <= {1'b0, operand_a} - {1'b0, operand_b};
                OP_AND : result <= {1'b0, operand_a & operand_b};
                OP_OR  : result <= {1'b0, operand_a | operand_b};
                OP_XOR : result <= {1'b0, operand_a ^ operand_b};
                OP_SHL : result <= {1'b0, operand_a} << operand_b[2:0];
                OP_SHR : result <= {1'b0, operand_a} >> operand_b[2:0];
                OP_NOP : result <= result;
            endcase

            zero_flag     <= (result[7:0] == 8'b0);
            overflow_flag <= result[8];
        end
    end

endmodule
