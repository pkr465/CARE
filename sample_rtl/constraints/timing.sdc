# =============================================================================
# CARE Sample SDC — Timing Constraints for sample_rtl
# =============================================================================
# Demonstrates: create_clock, create_generated_clock, set_false_path,
#               set_multicycle_path, set_input_delay, set_output_delay,
#               set_clock_groups
# =============================================================================

# --- Primary Clocks ---
create_clock -period 10.0 -name clk -waveform {0 5} [get_ports clk]
create_clock -period 15.0 -name clk_b [get_ports clk_b]

# --- Generated Clocks ---
create_generated_clock -source [get_ports clk] -divide_by 2 -name clk_div2

# --- Clock Groups (async domains) ---
set_clock_groups -asynchronous \
    -group {clk clk_div2} \
    -group {clk_b}

# --- False Paths ---
# The CDC between clk and clk_b in cdc_violation.v is intentional for testing
set_false_path -from [get_clocks clk] -to [get_clocks clk_b]
set_false_path -from [get_clocks clk_b] -to [get_clocks clk]

# --- Multicycle Paths ---
set_multicycle_path 2 -from [get_clocks clk] -to [get_clocks clk_div2]

# --- I/O Delays ---
set_input_delay 2.5 -clock clk [get_ports data_in]
set_input_delay 3.0 -clock clk_b [get_ports rx_data]
set_output_delay 1.8 -clock clk [get_ports data_out]
set_output_delay 2.0 -clock clk [get_ports tx_out]

# --- Max/Min Delay ---
set_max_delay 8.0 -from [get_ports data_in] -to [get_ports data_out]
set_min_delay 1.0 -from [get_ports clk] -to [get_ports tx_out]
