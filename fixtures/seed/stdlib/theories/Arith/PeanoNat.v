(** * Peano arithmetic on [nat]. A small demo slice of the Rocq standard library. *)

(** Addition on natural numbers is commutative. *)
Lemma add_comm : forall n m : nat, n + m = m + n.
Proof. Admitted.

(** Addition on natural numbers is associative. *)
Lemma add_assoc : forall n m p : nat, n + (m + p) = (n + m) + p.
Proof. Admitted.

(** Zero is a right identity for addition. *)
Lemma add_0_r : forall n : nat, n + 0 = n.
Proof. Admitted.

(** Multiplication on natural numbers is commutative. *)
Lemma mul_comm : forall n m : nat, n * m = m * n.
Proof. Admitted.

(** Multiplication distributes over addition on the right. *)
Lemma mul_add_distr_r : forall n m p : nat, (n + m) * p = n * p + m * p.
Proof. Admitted.

(** The strict order [<] on natural numbers is transitive. *)
Lemma lt_trans : forall n m p : nat, n < m -> m < p -> n < p.
Proof. Admitted.

(** The order [<=] on natural numbers is transitive. *)
Lemma le_trans : forall n m p : nat, n <= m -> m <= p -> n <= p.
Proof. Admitted.

(** Equality of natural numbers is decidable. *)
Definition eq_dec : forall n m : nat, {n = m} + {n <> m}.
Proof. Admitted.
