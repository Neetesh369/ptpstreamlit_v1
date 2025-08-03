import pandas as pd
import numpy as np
from app import calculate_zscore, calculate_rsi, calculate_hurst_exponent, test_johansen_cointegration

def test_calculations():
    """Test the key calculations to ensure they work correctly."""
    
    # Create test data
    dates = pd.date_range('2023-01-01', periods=100, freq='D')
    np.random.seed(42)
    
    # Create mean-reverting series for testing
    series1 = 100 + np.cumsum(np.random.randn(100) * 0.1)
    series2 = 50 + np.cumsum(np.random.randn(100) * 0.1) + 0.5 * series1  # Cointegrated with series1
    
    test_df = pd.DataFrame({
        'Date': dates,
        'Series1': series1,
        'Series2': series2
    })
    
    print("Testing calculations...")
    
    # Test Z-score calculation
    try:
        zscore = calculate_zscore(test_df['Series1'], window=20)
        print(f"✅ Z-score calculation: Mean={zscore.mean():.4f}, Std={zscore.std():.4f}")
    except Exception as e:
        print(f"❌ Z-score calculation failed: {e}")
    
    # Test RSI calculation
    try:
        rsi = calculate_rsi(test_df['Series1'], window=14)
        print(f"✅ RSI calculation: Mean={rsi.mean():.2f}, Range=[{rsi.min():.2f}, {rsi.max():.2f}]")
    except Exception as e:
        print(f"❌ RSI calculation failed: {e}")
    
    # Test Hurst exponent
    try:
        hurst = calculate_hurst_exponent(test_df['Series1'])
        print(f"✅ Hurst exponent: {hurst:.4f}")
    except Exception as e:
        print(f"❌ Hurst exponent calculation failed: {e}")
    
    # Test Johansen cointegration
    try:
        johansen_result = test_johansen_cointegration(test_df['Series1'], test_df['Series2'])
        print(f"✅ Johansen test: Cointegrated={johansen_result['Is Cointegrated']}")
        if johansen_result['Error'] is None:
            print(f"   Trace Statistic: {johansen_result['Trace Statistic']:.4f}")
            print(f"   Critical Value: {johansen_result['Critical Value']:.4f}")
    except Exception as e:
        print(f"❌ Johansen test failed: {e}")
    
    print("\nAll tests completed!")

if __name__ == "__main__":
    test_calculations()