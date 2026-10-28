#include <iostream>
#include <vector>

class Shape {
public:
    // area of a square
    int area(int s) { return s * s; }
};

int main() {
    Shape sh;
    for (int i = 0; i < 3; i++) {
        if (i % 2 == 0) { std::cout << sh.area(i) << std::endl; }
    }
    return 0;
}
