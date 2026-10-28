import java.util.*;
import java.sql.*;

public class UserService {
    // Looks up a user by name
    public ResultSet findUser(Connection c, String name) throws Exception {
        Statement st = c.createStatement();
        String sql = "SELECT * FROM users WHERE name = '" + name + "'";
        return st.executeQuery(sql);
    }

    public int score(int a, int b, int c) {
        if (a > b && b > c) { return a; }
        else if (a < 0 || b < 0) { return b; }
        try { return a / b; } catch (Exception e) { }
        return 0;
    }

    void run(String cmd) throws Exception {
        Runtime.getRuntime().exec(cmd);
    }
}
