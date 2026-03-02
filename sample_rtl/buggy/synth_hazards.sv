// ---------------------------------------------------------------------------
// Module : synth_hazards
// Description : Common synthesis hazards and anti-patterns
// BUG LIST:
//   1. Blocking assignment in sequential always_ff
//   2. Multiple drivers on the same signal
//   3. Combinational loop (circular dependency)
//   4. Unreachable states in FSM with no recovery
//   5. Non-full/non-parallel case without synthesis pragmas
// ---------------------------------------------------------------------------
module synth_hazards (
    input  logic       clk,
    input  logic       rst_n,
    input  logic [2:0] opcode,
    input  logic [7:0] din,
    output logic [7:0] dout,
    output logic       valid,
    output logic [7:0] acc
);

    // BUG 1: Blocking assignment (=) inside always_ff
    // Should use non-blocking (<=) for sequential logic
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            acc = 8'h00;        // ← blocking in sequential!
        else
            acc = acc + din;    // ← blocking in sequential!
    end

    // BUG 2: Multiple drivers — dout driven from two always blocks
    always_ff @(posedge clk) begin
        dout <= din;
    end

    always_comb begin
        dout = din ^ 8'hFF;    // ← second driver on dout!
    end

    // BUG 3: Combinational loop — a feeds b feeds a
    logic [7:0] loop_a, loop_b;

    always_comb begin
        loop_a = loop_b + 8'h01;  // ← circular
    end

    always_comb begin
        loop_b = loop_a - 8'h01;  // ← circular
    end

    // BUG 4: FSM with unreachable / dead states and no safe recovery
    typedef enum logic [2:0] {
        S_IDLE   = 3'b000,
        S_RUN    = 3'b001,
        S_DONE   = 3'b010,
        S_DEAD   = 3'b011,   // ← unreachable, no transition leads here
        S_UNUSED = 3'b100    // ← no transition out of this state
    } fsm_t;

    fsm_t state, next_state;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) state <= S_IDLE;
        else        state <= next_state;
    end

    always_comb begin
        next_state = state;
        valid      = 1'b0;
        case (state)
            S_IDLE : if (opcode[0]) next_state = S_RUN;
            S_RUN  : begin
                         valid = 1'b1;
                         if (opcode[1]) next_state = S_DONE;
                     end
            S_DONE : next_state = S_IDLE;
            // S_DEAD and S_UNUSED have no transitions — stuck forever
            default: ;  // ← does not recover to S_IDLE!
        endcase
    end

endmodule
