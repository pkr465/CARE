// ---------------------------------------------------------------------------
// Module : spi_master
// Description : Simple SPI master controller (SystemVerilog)
// ---------------------------------------------------------------------------
module spi_master #(
    parameter CLK_DIV  = 4,  // sclk = clk / (2 * CLK_DIV)
    parameter DATA_LEN = 8
)(
    input  logic              clk,
    input  logic              rst_n,
    // Control
    input  logic              start,
    input  logic [DATA_LEN-1:0] tx_data,
    output logic [DATA_LEN-1:0] rx_data,
    output logic              busy,
    output logic              done,
    // SPI pins
    output logic              sclk,
    output logic              mosi,
    input  logic              miso,
    output logic              cs_n
);

    typedef enum logic [1:0] {
        IDLE   = 2'b00,
        ACTIVE = 2'b01,
        FINISH = 2'b10
    } state_t;

    state_t              state, next_state;
    logic [$clog2(CLK_DIV)-1:0] clk_cnt;
    logic [$clog2(DATA_LEN)-1:0] bit_cnt;
    logic [DATA_LEN-1:0] shift_reg;
    logic                sclk_r;

    // State register
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            state <= IDLE;
        else
            state <= next_state;
    end

    // Next-state logic
    always_comb begin
        next_state = state;
        case (state)
            IDLE:    if (start) next_state = ACTIVE;
            ACTIVE:  if (bit_cnt == DATA_LEN-1 && clk_cnt == CLK_DIV-1 && sclk_r)
                         next_state = FINISH;
            FINISH:  next_state = IDLE;
            default: next_state = IDLE;
        endcase
    end

    // Datapath
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            clk_cnt   <= '0;
            bit_cnt   <= '0;
            shift_reg <= '0;
            sclk_r    <= 1'b0;
            rx_data   <= '0;
            done      <= 1'b0;
        end else begin
            done <= 1'b0;
            case (state)
                IDLE: begin
                    clk_cnt   <= '0;
                    bit_cnt   <= '0;
                    sclk_r    <= 1'b0;
                    if (start)
                        shift_reg <= tx_data;
                end
                ACTIVE: begin
                    if (clk_cnt == CLK_DIV-1) begin
                        clk_cnt <= '0;
                        sclk_r  <= ~sclk_r;
                        if (sclk_r) begin  // falling edge of sclk
                            shift_reg <= {shift_reg[DATA_LEN-2:0], miso};
                            bit_cnt   <= bit_cnt + 1'b1;
                        end
                    end else begin
                        clk_cnt <= clk_cnt + 1'b1;
                    end
                end
                FINISH: begin
                    rx_data <= shift_reg;
                    done    <= 1'b1;
                end
                default: ;
            endcase
        end
    end

    assign sclk = sclk_r;
    assign mosi = shift_reg[DATA_LEN-1];
    assign busy = (state != IDLE);
    assign cs_n = (state == IDLE);

endmodule
