#include <stdio.h>
#include <string.h>

/* reads a name from the user */
int main(void) {
    char name[16];
    char copy[16];
    gets(name);
    strcpy(copy, name);
    if (strlen(copy) > 3) {
        sprintf(name, "%s!", copy);
    }
    system("echo done");
    return 0;
}
