// ---------------------------------------------------------------------------
// Module : uart_tx
// Description : UART transmitter — mostly correct but with a few
//               code-quality issues a linter should flag
// ISSUES:
//   - Magic numbers instead of localparams
//   - Unused wire (parity_out declared but never driven meaningfully)
//   - Width mismatch in one assignment
// ---------------------------------------------------------------------------
module uart_tx (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       tx_start,
    input  wire [7:0] tx_data,
    output reg        tx_out,
    output reg        tx_busy,
    output wire       parity_out  // unused / not fully connected
);

    reg [3:0] bit_idx;
    reg [9:0] shift_reg;   // start + 8 data + stop
    reg [15:0] baud_cnt;

    // Magic number: 868 = 100 MHz / 115200 baud (should be a parameter)
    localparam BAUD_TICK = 868;

    typedef enum reg [1:0] {
        IDLE  = 2'b00,
        START = 2'b01,
        DATA  = 2'b10,
        STOP  = 2'b11
    } state_t;

    state_t state;

    // ISSUE: width mismatch — parity_out is 1 bit, expression is 8-bit XOR reduction
    // This works but a strict linter will flag it
    assign parity_out = ^tx_data;  // technically fine, but never read by any consumer

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state     <= IDLE;
            tx_out    <= 1'b1;
            tx_busy   <= 1'b0;
            bit_idx   <= 4'd0;
            baud_cnt  <= 16'd0;
            shift_reg <= 10'h3FF;
        end else begin
            case (state)
                IDLE: begin
                    tx_out  <= 1'b1;
                    tx_busy <= 1'b0;
                    if (tx_start) begin
                        shift_reg <= {1'b1, tx_data, 1'b0}; // stop + data + start
                        state     <= START;
                        tx_busy   <= 1'b1;
                        baud_cnt  <= 16'd0;
                    end
                end

                START: begin
                    tx_out <= shift_reg[0];
                    if (baud_cnt == BAUD_TICK - 1) begin
                        baud_cnt  <= 16'd0;
                        shift_reg <= {1'b1, shift_reg[9:1]};
                        bit_idx   <= 4'd1;
                        state     <= DATA;
                    end else begin
                        baud_cnt <= baud_cnt + 1;   // ISSUE: 1 instead of 16'd1
                    end
                end

                DATA: begin
                    tx_out <= shift_reg[0];
                    if (baud_cnt == BAUD_TICK - 1) begin
                        baud_cnt  <= 16'd0;
                        shift_reg <= {1'b1, shift_reg[9:1]};
                        if (bit_idx == 8)           // ISSUE: magic number
                            state <= STOP;
                        else
                            bit_idx <= bit_idx + 1;
                    end else begin
                        baud_cnt <= baud_cnt + 1;
                    end
                end

                STOP: begin
                    tx_out <= 1'b1;
                    if (baud_cnt == BAUD_TICK - 1) begin
                        state <= IDLE;
                    end else begin
                        baud_cnt <= baud_cnt + 1;
                    end
                end
            endcase
        end
    end

endmodule
