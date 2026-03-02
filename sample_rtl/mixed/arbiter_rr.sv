// ---------------------------------------------------------------------------
// Module : arbiter_rr
// Description : Round-robin arbiter — functional but with style issues
// ISSUES:
//   - Priority encoding could mask starvation under heavy load
//   - No parameterisation — hardcoded to 4 requestors
//   - Inconsistent signal naming (camelCase vs snake_case)
// ---------------------------------------------------------------------------
module arbiter_rr (
    input  logic       clk,
    input  logic       rst_n,
    input  logic [3:0] req,
    output logic [3:0] grant,
    output logic       grantValid  // ISSUE: camelCase in mostly snake_case module
);

    logic [1:0] last_grant;
    logic [3:0] masked_req;
    logic [3:0] next_grant;

    // Mask out requests at or below last-granted priority
    always_comb begin
        case (last_grant)
            2'd0: masked_req = req & 4'b1110;
            2'd1: masked_req = req & 4'b1100;
            2'd2: masked_req = req & 4'b1000;
            2'd3: masked_req = req & 4'b0000;
        endcase
    end

    // Priority encode masked requests; fall back to unmasked
    always_comb begin
        if      (masked_req[0]) next_grant = 4'b0001;
        else if (masked_req[1]) next_grant = 4'b0010;
        else if (masked_req[2]) next_grant = 4'b0100;
        else if (masked_req[3]) next_grant = 4'b1000;
        else if (req[0])        next_grant = 4'b0001;
        else if (req[1])        next_grant = 4'b0010;
        else if (req[2])        next_grant = 4'b0100;
        else if (req[3])        next_grant = 4'b1000;
        else                    next_grant = 4'b0000;
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            grant      <= 4'b0000;
            grantValid <= 1'b0;
            last_grant <= 2'd0;
        end else begin
            grant      <= next_grant;
            grantValid <= |next_grant;
            case (next_grant)
                4'b0001: last_grant <= 2'd0;
                4'b0010: last_grant <= 2'd1;
                4'b0100: last_grant <= 2'd2;
                4'b1000: last_grant <= 2'd3;
                default: last_grant <= last_grant;
            endcase
        end
    end

endmodule
