(** * ssrnat. A small demo slice of Mathematical Components. *)

(** Addition on natural numbers is commutative. *)
Lemma addnC : commutative addn.
Proof. Admitted.

(** Addition on natural numbers is associative. *)
Lemma addnA : associative addn.
Proof. Admitted.

(** Multiplication on natural numbers is commutative. *)
Lemma mulnC : commutative muln.
Proof. Admitted.

(** Multiplication distributes over addition. *)
Lemma mulnDr : right_distributive muln addn.
Proof. Admitted.

(** Transitivity of the strict order on natural numbers. *)
Lemma ltn_trans : forall n m p, m < n -> n < p -> m < p.
Proof. Admitted.

(** Boolean equality on natural numbers reflects propositional equality. *)
Lemma eqnP : forall m n, reflect (m = n) (eqn m n).
Proof. Admitted.
